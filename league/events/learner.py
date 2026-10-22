"""PREREG-EVL-7's TWO ONLINE LEARNERS, EVL-LRN-O1 and EVL-LRN-ON (docs/prereg/PREREG-EVL-7.md once frozen; until then
the draft `goal-2026-10-19/evl7/PREREG-EVL-7.draft.md` as the captain's decisions E1-E11 change it). Standard library
only. Nothing here runs while league/events/programs.py `REGISTERED_AT_7` is None: the learners are in no registry, so
no decision, no trade and no charge (E3).

EACH DECISION (`decide`), for learner L and entry session D at its tau (09:15 ET for EVL-LRN-O1, the close less 14
minutes for EVL-LRN-ON), reads ONLY THE STORE, every cut-off from stored times as of tau (section 1.11 item 2):

1. CANDIDATES (section 1.3): for each pool program p in pool order (`POOLS`), the events its own rule takes for D read
   as real money reads them, league/events/book.py `picks(lane, p, D, decided_at=tau)` over a view of the store whose
   LIVE eligibility is TIME-BOUND (E5, `eligible_by`: the live rule's eligible result decided at or before the finish
   of the House's own decision of that auction, and never after the learner's entry auction); the book's reaction
   reading from STORED marks and bars only. ONE CANDIDATE PER CIK: its pool families, its primary event (the first
   family's, in pool order). KEPT when TRADABLE at decision (1.25 x prev_close <= 10% of E_prev); ELIGIBLE TO BE
   PICKED when kept, its primary event knowable after REGISTERED_AT_7, and the learner holds no intent of the issuer
   inside PREREG-EVL-1 section 5's five sessions either way (programs.py `_held_recently`, A72; every written,
   non-skipped intent of the id and version, the catch-up's included).
2. FEATURES (section 1.4; `FEATURES`): 57 columns for EVL-LRN-O1, 63 for EVL-LRN-ON, each from rows stored before tau,
   written once with the candidate (`learner_cands`), never recomputed. The 16 headline flags and `dup72` are the
   reader lens's frozen `KEYWORDS`, `words`, `STOP` and `jaccard` (goal-2026-10-19/evl7/reader/features_spec.py,
   sha256 `SPEC_SHA`), copied here verbatim. EVL-LRN-ON's `dmove` reads D's '1530' mark by its own bar time before tau,
   whatever its fetch time (E6); the live close decision fetches the candidates' marks in its batched requests first.
3. TRAINING ROWS (section 1.5): every KEPT candidate of every earlier entry session of the learner (at most 250
   sessions back) whose POOL OUTCOME (the first pool program in pool order holding an intent of the issuer entering at
   s at the learner's auctions with an outcome `settled`, `tradable` 1, `settled_at` before tau and a raw entry print at
   most 1.25 x the previous SIP close) exists; its features as stored at its own tau; the GROSS abnormal label (E7)
   y = clip(a_g / sig20, -5, 5), a_g = exit_px / entry_px - bench_exit / bench_entry (no cost column is read).
4. THE FIT (section 1.5): weights 2^(-age / 40); within-session demeaning; A = sum_s w_s sum_i x~ x~', b = sum_s w_s
   sum_i x~ y~, N_w = sum_s w_s n_s, each a `math.fsum` in (entry day, CIK) order (the inner sums per session, the outer
   over sessions in day order); d_j = sqrt(A_jj / N_w) (a column under 1e-9 set to 1 and zeroed); M = D^-1 A D^-1 +
   8000 I solved by a CHOLESKY in float64 (`cholesky`, stdlib; section 1.11 item 6 names numpy's, which league/ may not
   import: the same factorization, every inner sum a `math.fsum`). The per-session sums are CACHED (`learner_stats`)
   under (program, version, session, the sha256 of the session's ordered training keys, the code sha): a session
   settled further is a new key.
5. THE PICK (section 1.6): e_i = (x_i - xbar_D) . beta, c_i the replay's round trip (score.py `cost_bp`, entry plus
   exit, at its adv20 and E_prev), z_i = e_i - c_i / sig20_i, ahat_i = sig20_i z_i; the eligible candidates with z_i > 0
   ranked by ahat, then adv20, then the event id; the first 8 are its intents (`intents.rank_key` = ahat). The level
   is never learned. WARM-UP: no pick before 2,000 training rows from 3 sessions. FAIL CLOSED: no E_prev, a fit that
   is not finite or a Cholesky that fails picks nothing, its fits row says why.

ONE DECISION, WRITTEN ONCE: the candidates, the fit and the picks in one transaction; a decision on record is never
decided again. Its KIND: `live` (the House's own decision of the auction, run right after that decision's receipt
finished, under its own time bound: `BOUND_S`; league/events/run.py `learner_part`), `catchup` (THE DECISIONS BEFORE
THE RELEASE, E4) and `late` (a live part that failed or ran past its bound), both decided later by themselves exactly
as of tau under receipts `decide-open-lrn:<D>` / `decide-close-lrn:<D>` (`RECEIPT`), shadow only, never traded and never
judged; `reconstruct` (the candidate sets of the sessions before REGISTERED_AT_7, once, as of each session's own tau,
section 1.5). Every fits row records `CODE_SHA`, the sha256 of this file's own bytes. A NIGHTLY RECOMPUTE (`recompute`)
decides the night's live decisions again in memory and compares beta and the picks where the stored inputs are
unchanged; it alarms on any other mismatch with its cause and never rewrites a decision.

WHAT IS MACHINE-ONLY: beta, d, xbar, e, z, ahat and the per-session sums are outcome-derived fitted figures. They live
in `learner_fits`, `learner_cands` and `learner_stats` (and `intents.rank_key`, the order the text pins); no report,
site or births reads them (`report_lines` gives picks and training rows only; R3's facts refuse these tables,
league/events/births.py `FACTS_DENY`)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import operator
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import programs as P
from . import store as S
from . import verdicts as V

# ----------------------------------------------------------------------------------------------------- the constants
#: Section 1.2: each learner's pool, version 1 of each program, in this order (the primary family is the first).
POOLS: dict[str, tuple[str, ...]] = {
    "EVL-LRN-O1": ("EVL-CTRL-NEWS-ALL-O1", "EVL-CTRL-8K-ALL-O1", "EVL-CTRL-ERN-ALL-O1", "EVL-INS-BUY-O1"),
    "EVL-LRN-ON": ("EVL-CTRL-NEWS-DAY-ON", "EVL-CTRL-NEWSPM-ON", "EVL-CTRL-8K-ON", "EVL-ERN-REACT-ON", "EVL-ERN-DROP-ON",
                   "EVL-CTRL-ERN-UNDER-ON"),
}
K = 8                       # section 1.6: at most 8 intents a decision
LAMBDA = 8000.0             # section 1.5: ridge on standardized columns
HALF_LIFE = 40.0            # section 1.5: w_s = 2^(-age / 40)
LOOKBACK = 250              # section 1.5: at most 250 sessions back
WARM_ROWS = 2000            # section 1.7: the warm-up
WARM_SESSIONS = 3
LABEL_CLIP = 5.0            # section 1.5: y = clip(a_g / sig20, -5, 5)
D_FLOOR = 1e-9              # section 1.5: a column with d_j < 1e-9 is set to 1 and zeroed
SIG_FLOOR, SIG_CAP, SIG_MISSING = 0.005, 0.25, 0.03     # section 1.4 items 10 and 12
CLOSES = 20                 # section 1.4 item 10: the 20 latest stored raw closes of sessions before D
LIMIT_MULTIPLE = 1.25       # TRADABLE and the pool outcome's limit at entry (PREREG-EVL-1 section 5, PREREG-EVL-2)
TRADABLE_SHARE = 0.10
ADV_SCALE, PRICE_SCALE, SIG_SCALE, INS_SCALE = 1e7, 20.0, 0.03, 50_000.0
DUP_WINDOW = dt.timedelta(hours=72)     # section 1.4 item 13
BACK_SESSIONS = 20          # section 1.4 item 8: n_att20 and first20
#: Section 1.7 / 1.11 item 8: the learner part's own time bound (seconds from its start), and never past the task's
#: own bound less FINISH_S (the part never holds the House's task to its end).
BOUND_S = {"open": 90.0, "close": 120.0}
FINISH_S = 15.0
#: Section 1.11 item 9: the receipts of a decision made by the learners by themselves (the catch-up, a failed part's).
RECEIPT = {"open": "decide-open-lrn", "close": "decide-close-lrn"}
KINDS = ("live", "catchup", "late", "reconstruct")
#: A catch-up decision that raised is tried again this many times, then written closed (it picks nothing).
CATCHUP_TRIES = 3
#: The live part's own record when it did not write a decision (meta `PART_KEY`): failed or expired, why, when.
PART_KEY = "evl7:part:{program}:{version}:{day}"
#: meta: the reconstruction of the candidate sets before REGISTERED_AT_7 has run (once).
RECONSTRUCTED_KEY = "evl7:reconstructed:{program}:{version}"
#: meta: the nightly recompute's result for a session day ({program@vN: {status, cause, ...}}).
RECOMPUTE_KEY = "evl7:recompute:{day}"
#: The O1 learner's knowable-hour buckets (section 1.4 item 14) and the ON learner's (item 15), ET wall times.
OVERNIGHT_FROM, OVERNIGHT_TO = dt.time(20, 0), dt.time(4, 0)
PRE_TO, LATE_TO = dt.time(7, 0), dt.time(9, 0)
MORNING_FROM, MORNING_TO = dt.time(9, 0), dt.time(12, 0)
ITEMS = ("1.01", "2.01", "7.01", "8.01")
SIC_GROUPS = (("bio", ((2833, 2836), (8731, 8731))), ("tech", ((3570, 3579), (3600, 3699), (7370, 7379))),
              ("fin", ((6000, 6799),)), ("energy", ((1000, 1499), (2900, 2999))))

# ------------------------------------------------------------- the reader lens's frozen headline features (verbatim)
#: goal-2026-10-19/evl7/reader/features_spec.py, sha256 below (copied into docs/prereg/evl-7/ at the freeze): its
#: `STOP`, `KEYWORDS`, `words` and `jaccard`, word for word (league/tests/test_events_evl7.py holds them equal).
SPEC_SHA = "b2f3aaaacccff9194b142b51e13e6a926cc1c18ff1b00682c87e9f97ecdcab85"
STOP = frozenset("the and for with from that this its are was has have will into over after amid about stock shares "
                 "inc corp co ltd plc company announces reports says".split())
#: Headline flags (case-insensitive), frozen.
KEYWORDS = {
    "kw_upgrade": r"\bupgrade[sd]?\b", "kw_downgrade": r"\bdowngrade[sd]?\b", "kw_initiate": r"\binitiat\w*",
    "kw_pt": r"\bprice target\b", "kw_raise": r"\b(raises?|raised|boosts?|lifts?)\b",
    "kw_cut": r"\b(lowers?|lowered|cuts?|slashes?|reduces?)\b", "kw_beat": r"\bbeats?\b", "kw_miss": r"\bmiss(es)?\b",
    "kw_fda": r"\b(fda|approval|approves?|cleared)\b", "kw_deal": r"\b(acquir\w*|merger|to buy|buyout|takeover)\b",
    "kw_offering": r"\b(offering|private placement|at-the-market)\b",
    "kw_buyback": r"\b(buyback|repurchase)\b", "kw_dividend": r"\bdividend\b", "kw_contract": r"\b(contract|awarded)\b",
    "kw_guidance": r"\b(guidance|outlook|sees|forecast)\b",
    "kw_move": r"(shares are trading|stock is (moving|trading|up|down)|why is|shares (rise|fall|jump|drop|slide|soar)"
               r"|trading (higher|lower)|\bmovers?\b)",
}
_KW = {k: re.compile(v, re.I) for k, v in KEYWORDS.items()}


def words(headline: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9'-]{2,}", (headline or "").lower()) if w not in STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# ------------------------------------------------------------------------------------------------------ the features
def feature_names(program: str) -> tuple[str, ...]:
    """Section 1.4's columns of `program`, in their order (57 for EVL-LRN-O1, 63 for EVL-LRN-ON)."""
    pool = POOLS[program]
    dummies = tuple(f"pool_{p}" for p in pool[1:])
    out = dummies + ("multi", "s_num", "s_ge2", "s_eq3", "s_le_m1", "no_score") + tuple(f"s_x_{d}" for d in dummies)
    out += ("guide_raised", "guide_lowered") + tuple(f"item_{i}" for i in ITEMS) + ("src_benzinga", "n_art", "n_att20",
                                                                                      "first20", "mon", "fri")
    out += ("ln_adv20", "ln_prev_close", "ln_sig20", "bench_iwm") + tuple(f"sic_{g}" for g, _ in SIC_GROUPS)
    out += ("r1", "r5", "r20", "hist_missing") + tuple(KEYWORDS) + ("dup72",)
    if program == "EVL-LRN-O1":
        out += ("overnight", "pre", "late", "ln_ins")
    else:
        out += ("morning", "before", "dmove", "dmove_missing", "abs_dmove", "s_x_dmove")
    return out


FEATURES = {program: feature_names(program) for program in POOLS}


def _code_sha() -> str:
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return "unknown"


#: Section 1.7 / 1.11: the learner code's identity every fits row records (the sha256 of this file's bytes; the release
#: that carries it pins its commit). A cache entry of another code is never read.
CODE_SHA = _code_sha()

SCHEMA = """
CREATE TABLE IF NOT EXISTS learner_fits(program TEXT NOT NULL, version INTEGER NOT NULL, day TEXT NOT NULL,
  tau TEXT NOT NULL, kind TEXT NOT NULL, receipt TEXT, receipt_id INTEGER, status TEXT NOT NULL, why TEXT,
  n_cands INTEGER, n_kept INTEGER, n_rows INTEGER, n_sessions INTEGER, n_picks INTEGER, keys_sha TEXT, code_sha TEXT,
  beta TEXT, d TEXT, xbar TEXT, eligible_by TEXT, train_last TEXT, started_at TEXT, finished_at TEXT NOT NULL,
  PRIMARY KEY(program, version, day));
CREATE TABLE IF NOT EXISTS learner_cands(program TEXT NOT NULL, version INTEGER NOT NULL, day TEXT NOT NULL,
  cik TEXT NOT NULL, event TEXT NOT NULL, symbol TEXT, families TEXT NOT NULL, kept INTEGER NOT NULL,
  eligible INTEGER NOT NULL, features TEXT, sig20 REAL, adv20 REAL, prev_close REAL, knowable_at TEXT, e REAL, z REAL,
  ahat REAL, picked INTEGER NOT NULL, rank INTEGER, kind TEXT NOT NULL, PRIMARY KEY(program, version, day, cik));
CREATE TABLE IF NOT EXISTS learner_stats(program TEXT NOT NULL, version INTEGER NOT NULL, day TEXT NOT NULL,
  keys_sha TEXT NOT NULL, code_sha TEXT NOT NULL, n INTEGER NOT NULL, stats TEXT NOT NULL,
  PRIMARY KEY(program, version, day, keys_sha, code_sha));
"""
#: The tables this module writes (additive; SCHEMA_VERSION stays 1). Outcome-derived: R3's facts refuse every one.
TABLES = ("learner_fits", "learner_cands", "learner_stats")


def ensure(db: Any) -> None:
    """The learner's tables on a store (additive, idempotent)."""
    db.executescript(SCHEMA)


class Expired(Exception):
    """The learner part ran past its own time bound (section 1.7): nothing is written; decided later by itself."""


@dataclasses.dataclass
class Cand:
    """One candidate of a decision: its issuer, its pool families' picks (pool order), and what is computed for it."""

    cik: str
    picks: dict[str, Any]
    families: list[str]
    uni: Mapping[str, Any]
    kept: bool = False
    eligible: bool = False
    x: list[float] | None = None
    sig20: float = SIG_MISSING
    hist: bool = False
    e: float | None = None
    z: float | None = None
    ahat: float | None = None
    rank: int | None = None

    @property
    def primary(self) -> Any:
        return self.picks[self.families[0]]

    @property
    def event(self) -> str:
        return str(self.primary.event)

    @property
    def adv20(self) -> float:
        try:
            return float(self.uni.get("adv20") or 0.0)
        except (TypeError, ValueError):
            return 0.0


# ----------------------------------------------------------------------------------------------- the as-of reading
class AsOf:
    """THE LANE'S STORE READ AS OF A LEARNER DECISION: the store's own connection (read only by everything here), the
    book's per-decision cache, the documents, and THE ELIGIBILITY BOUND (E5) league/events/book.py `universe_rows`
    reads (`eligible_by`): a live result counts only when decided at or before it."""

    def __init__(self, store: Any, eligible_by: dt.datetime | None):
        self.store = store
        self.db = store.db
        self.root = getattr(store, "root", None)
        self.cache: dict[str, Any] = {}
        self.eligible_by = eligible_by

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def get_document(self, digest: str) -> bytes:
        return self.store.get_document(digest)


def tau_of(store: Any, program: P.Program, day: dt.date) -> dt.datetime | None:
    """The learner's decision time of entry session `day` (section 1.2), None when the calendar holds no such session."""
    session = C.session(store, day)
    if session is None:
        return None
    return session.open_decide if program.entry_at == "open" else session.close_decide


def entry_auction(store: Any, program: P.Program, day: dt.date) -> dt.datetime | None:
    session = C.session(store, day)
    if session is None:
        return None
    return session.open_at if program.entry_at == "open" else session.close_at


def house_receipt(store: Any, program: P.Program, day: dt.date) -> Mapping[str, Any] | None:
    """THE HOUSE'S OWN DECISION OF THE AUCTION (E5): the earliest `decide-open:<D>` (EVL-LRN-O1) or `decide-close:<D>`
    (EVL-LRN-ON) receipt finished `ok` or `pending`, as league/events/book.py `decided` reads the lane's decision as
    having run; {id, finished_at, started_at}, or None."""
    job = f"decide-{program.entry_at}:{day.isoformat()}"
    row = store.db.execute("SELECT id, started_at, finished_at FROM receipts WHERE job=? AND finished_at IS NOT NULL AND "
                           "status IN ('ok', 'pending') ORDER BY id LIMIT 1", (job,)).fetchone()
    return None if row is None else dict(row)


def eligible_by(store: Any, program: P.Program, day: dt.date) -> dt.datetime | None:
    """E5's BOUND: the finish of the House's own decision of the auction (`house_receipt`), and never later than the
    learner's entry auction (09:30 ET of D for EVL-LRN-O1, D's close for EVL-LRN-ON). None with no such decision (then
    no issuer is a candidate)."""
    got = house_receipt(store, program, day)
    if got is None:
        return None
    try:
        finished = S.parse_iso(str(got["finished_at"]))
    except (TypeError, ValueError):
        return None
    entry = entry_auction(store, program, day)
    return finished if entry is None else min(finished, entry)


def _before(text: Any, tau: dt.datetime) -> bool:
    """A stored time strictly before tau (section 1.1); an unreadable time is not (fail closed)."""
    try:
        return S.parse_iso(str(text)) < tau
    except (TypeError, ValueError):
        return False


def equity_prev(store: Any, day: dt.date) -> float | None:
    """E_prev: the account equity at the previous session's close as score.py reads it (`equity_on`)."""
    from . import score as SC

    prior = C.previous(store, day, 1)
    return SC.equity_on(store, prior[0].day) if prior else None


def tradable(prev_close: Any, equity: float | None) -> bool:
    """TRADABLE at decision (section 1.1): 1.25 x the universe row's prev_close <= 10% of E_prev."""
    try:
        prev = float(prev_close)
    except (TypeError, ValueError):
        return False
    return equity is not None and math.isfinite(prev) and prev > 0 and LIMIT_MULTIPLE * prev <= TRADABLE_SHARE * equity


# ------------------------------------------------------------------------------------------------------ candidates
def pool_programs(learner: P.Program, tau: dt.datetime) -> list[P.Program]:
    """The learner's pool programs that are live at tau (section 1.2: a pool program not yet live contributes no
    candidate): each version 1 row of the pool this process knows whose registration time is before tau."""
    out = []
    for pid in POOLS[learner.id]:
        prog = P.BY_KEY.get((pid, 1))
        if prog is None:
            continue
        try:
            if prog.registered_at >= tau:
                continue
        except (RuntimeError, ValueError):
            continue
        out.append(prog)
    return out


def candidates(store: Any, learner: P.Program, day: dt.date, tau: dt.datetime, bound: dt.datetime | None
               ) -> tuple[list[Cand], dict[str, Any]]:
    """Section 1.3's candidates of `learner` for entry session `day` at `tau`, one per CIK in (pool order of the
    primary family, CIK) order, with the counts. `bound`: E5's eligibility bound (None: no candidate)."""
    from . import book as EB

    counts: dict[str, Any] = {"pool": {}}
    if bound is None:
        counts["why"] = "no finished House decision of the auction: no live eligibility, no candidate (E5)"
        return [], counts
    view = AsOf(store, bound)
    reaction = None
    if learner.entry_at == "close":
        reaction = EB.reaction_reader(view, day, daily=lambda symbol, d: None, minutes=lambda symbol, session: None)
    uni = EB.universe_rows(view, day)
    merged: dict[str, Cand] = {}
    order: list[str] = []
    for prog in pool_programs(learner, tau):
        got = EB.picks(view, prog, day, decided_at=tau, reaction=reaction)
        counts["pool"][prog.id] = len(got)
        for pick in got:
            cik = str(pick.cik)
            if not cik or cik not in uni:
                continue
            have = merged.get(cik)
            if have is None:
                merged[cik] = Cand(cik, {prog.id: pick}, [prog.id], uni[cik])
                order.append(cik)
            elif prog.id not in have.picks:
                have.picks[prog.id] = pick
                have.families.append(prog.id)
    pool = POOLS[learner.id]
    out = sorted(merged.values(), key=lambda c: (pool.index(c.families[0]), c.cik))
    counts["candidates"] = len(out)
    return out, counts


# ----------------------------------------------------------------------------------------------- the feature reads
def _sessions_back(store: Any, day: dt.date, n: int) -> list[C.Session]:
    return C.previous(store, day, n)


def _closes(store: Any, symbol: str, day: dt.date) -> list[float]:
    """The latest CLOSES raw SIP daily closes of sessions before `day` (latest first), positive and finite only."""
    out = []
    for r in store.db.execute("SELECT day, c FROM bars WHERE symbol=? AND adj='raw' AND day<? ORDER BY day DESC LIMIT ?",
                              (str(symbol).upper(), day.isoformat(), CLOSES)):
        try:
            c = float(r["c"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(c) and c > 0:
            out.append(c)
    return out


def sig20_of(closes: Sequence[float]) -> float | None:
    """Section 1.4 item 10 (section 1.11 item 4): the SAMPLE standard deviation (divisor 18) of the 19 daily log changes
    of 20 closes, before any floor or cap; None with fewer than 20 closes."""
    if len(closes) < CLOSES:
        return None
    logs = [math.log(closes[i] / closes[i + 1]) for i in range(CLOSES - 1)]
    mean = math.fsum(logs) / len(logs)
    return math.sqrt(math.fsum((v - mean) ** 2 for v in logs) / (len(logs) - 1))


def _clip(v: float, cap: float) -> float:
    return max(-cap, min(cap, v))


def _sic(store: Any, cik: str) -> int | None:
    row = store.db.execute("SELECT sic FROM cik_info WHERE cik=?", (str(cik),)).fetchone()
    try:
        return int(str(row["sic"]).strip()) if row is not None and row["sic"] is not None else None
    except (TypeError, ValueError):
        return None


def _event_row(store: Any, event: str) -> dict[str, Any] | None:
    kind, _, ident = str(event).partition(":")
    if kind in ("8k", "f4"):
        row = store.db.execute("SELECT * FROM filings WHERE accession=?", (ident,)).fetchone()
    elif kind == "news":
        row = store.db.execute("SELECT * FROM news WHERE id=?", (ident,)).fetchone()
    else:
        return None
    return None if row is None else dict(row)


def _verdict(store: Any, event: str, tau: dt.datetime) -> Mapping[str, Any] | None:
    """The stored verdict of a pool event answered before tau with status `ok` (PROMPT-NEWS for an article, PROMPT-DOC
    for an 8-K), else None (section 1.4 item 3)."""
    kind = str(event).partition(":")[0]
    if kind not in ("news", "8k"):
        return None
    got = V.stored(store, event, V.PROMPTS["news" if kind == "news" else "doc"])
    if not got or got.get("status") != "ok" or got.get("score") is None or not _before(got.get("answered_at"), tau):
        return None
    return got


def _windows(store: Any, pid: str, day: dt.date) -> tuple[dt.datetime, dt.datetime] | None:
    """The window of pool program `pid`'s events for entry session `day` (section 1.11 item 3: the primary pool
    program's own window, programs.py)."""
    prog = P.BY_KEY.get((pid, 1))
    if prog is None:
        return None
    try:
        if prog.family == "news":
            return P.news_window(store, day)
        if prog.family in ("news-day",):
            return P.day_news_window(store, day)
        if prog.family == "news-pm":
            return P.news_window(store, day)
        if prog.entry_at == "open":
            return P.open_window(store, day)
        return P.close_window(store, day)
    except LookupError:
        return None


class Reads:
    """One decision's reads for the features, each made once (section 1.11 items 2-4)."""

    def __init__(self, store: Any, learner: P.Program, day: dt.date, tau: dt.datetime):
        self.store, self.learner, self.day, self.tau = store, learner, day, tau
        self.session = C.session(store, day)
        back = _sessions_back(store, day, BACK_SESSIONS)
        self.back = back
        self._counts: dict[tuple[dt.datetime, dt.datetime], dict[str, int]] = {}
        self._named: list[tuple[dt.datetime, set[str], str]] | None = None
        prev = C.previous(store, day, 1)
        nxt = C.nth(store, day, 2)
        week = day.isocalendar()[:2]
        self.mon = int(not prev or prev[0].day.isocalendar()[:2] != week)
        self.fri = int(nxt is not None and nxt.day.isocalendar()[:2] != week)
        self.recent = self._recent_kept()

    def _recent_kept(self) -> set[str]:
        """The CIKs of this learner's KEPT candidate sets of the previous 20 sessions (section 1.4 item 8's first20)."""
        if not self.back:
            return set()
        days = [s.day.isoformat() for s in self.back]
        return {str(r[0]) for r in self.store.db.execute(
            f"SELECT DISTINCT cik FROM learner_cands WHERE program=? AND version=? AND kept=1 AND day IN "
            f"({', '.join('?' * len(days))})", (self.learner.id, self.learner.version, *days))}

    def single_counts(self, lo: dt.datetime, hi: dt.datetime) -> dict[str, int]:
        """{symbol: single-symbol articles knowable in (lo, hi] stored before tau} (PREREG-EVL-1 section 3's non-live
        exclusion applied, programs.py `news_rows`)."""
        key = (lo, hi)
        if key not in self._counts:
            got: dict[str, int] = {}
            for a in P.news_rows(self.store, lo, hi):
                if _before(a.get("received_at"), self.tau):
                    got[a["symbol"]] = got.get(a["symbol"], 0) + 1
            self._counts[key] = got
        return self._counts[key]

    def named(self, symbol: str, k: dt.datetime) -> list[str]:
        """The headlines of every stored article naming `symbol` (any number of symbols) knowable in [k - 72 h, k) and
        stored before tau (section 1.4 item 13's dup72)."""
        if self._named is None:
            lo = self.tau - DUP_WINDOW - dt.timedelta(days=7)
            rows = []
            for r in self.store.db.execute("SELECT knowable_at, received_at, symbols, headline FROM news WHERE "
                                           "knowable_at>=? AND knowable_at<?", (S.iso(lo), S.iso(self.tau))):
                if not _before(r["received_at"], self.tau):
                    continue
                try:
                    syms = {str(x).upper() for x in (json.loads(r["symbols"] or "[]") or []) if x is not None}
                    at = S.parse_iso(str(r["knowable_at"]))
                except (TypeError, ValueError):
                    continue
                rows.append((at, syms, str(r["headline"] or "")))
            self._named = rows
        lo = k - DUP_WINDOW
        return [h for at, syms, h in self._named if lo <= at < k and symbol in syms]

    def mark_1530(self, symbol: str) -> float | None:
        """EVL-LRN-ON's m1530 (E6): D's '1530' mark of the ticker, its own bar time before tau, whatever its fetch time."""
        row = self.store.db.execute("SELECT px, t FROM marks WHERE symbol=? AND day=? AND label='1530'",
                                    (symbol, self.day.isoformat())).fetchone()
        if row is None or row["px"] is None or not _before(row["t"], self.tau):
            return None
        try:
            px = float(row["px"])
        except (TypeError, ValueError):
            return None
        return px if math.isfinite(px) and px > 0 else None


def features(reads: Reads, cand: Cand) -> tuple[list[float], float, bool]:
    """Section 1.4's vector x of a candidate (`FEATURES` order), its sig20 (item 10 or 12) and hist_missing."""
    st, learner, day, tau = reads.store, reads.learner, reads.day, reads.tau
    pool = POOLS[learner.id]
    names = FEATURES[learner.id]
    v: dict[str, float] = {n: 0.0 for n in names}
    primary_family = cand.families[0]
    for p in pool[1:]:
        v[f"pool_{p}"] = float(primary_family == p)
    v["multi"] = float(len(cand.families) >= 2)
    # item 3: the BEST ok verdict answered before tau among the candidate's pool events
    best = None
    for fam in cand.families:
        pick = cand.picks[fam]
        got = _verdict(st, str(pick.event), tau)
        if got is None:
            continue
        knowable = S.parse_iso(str(pick.knowable_at))
        key = (-int(got["score"]), knowable, str(pick.event))
        if best is None or key < best[0]:
            best = (key, got, str(pick.event))
    if best is None:
        v["no_score"] = 1.0
        s_num = 0.0
    else:
        score = int(best[1]["score"])
        s_num = score / 3.0
        v["s_num"], v["s_ge2"], v["s_eq3"], v["s_le_m1"] = s_num, float(score >= 2), float(score == 3), float(score <= -1)
        if best[2].startswith("8k:"):
            v["guide_raised"] = float(best[1].get("guidance") == "raised")
            v["guide_lowered"] = float(best[1].get("guidance") == "lowered")
    for p in pool[1:]:
        v[f"s_x_pool_{p}"] = s_num * v[f"pool_{p}"]
    primary = cand.primary
    row = _event_row(st, str(primary.event)) or {}
    if str(primary.event).startswith("8k:"):
        items = P.items_of(row)
        for it in ITEMS:
            v[f"item_{it}"] = float(it in items)
    symbol = str(cand.uni.get("symbol") or primary.symbol).upper()
    news_primary = str(primary.event).startswith("news:")
    if news_primary:
        v["src_benzinga"] = float("benzinga" in str(row.get("source") or "").lower())
    # item 8: n_art, n_att20 and first20
    win = _windows(st, primary_family, day)
    if win is not None:
        v["n_art"] = math.log1p(reads.single_counts(*win).get(symbol, 0))
        back = reads.back
        far = _windows(st, primary_family, back[0].day) if len(back) >= BACK_SESSIONS else None
        lo20 = far[0] if far is not None else (back[0].open_at if back else win[0])
        v["n_att20"] = math.log1p(reads.single_counts(lo20, win[0]).get(symbol, 0))
    v["first20"] = float(cand.cik not in reads.recent)
    v["mon"], v["fri"] = float(reads.mon), float(reads.fri)
    # items 10-12: the issuer
    adv = cand.adv20
    prev = float(cand.uni.get("prev_close") or 0.0)
    v["ln_adv20"] = math.log(adv / ADV_SCALE) if adv > 0 else 0.0
    v["ln_prev_close"] = math.log(prev / PRICE_SCALE) if prev > 0 else 0.0
    v["bench_iwm"] = float(str(cand.uni.get("bench") or "").upper() == "IWM")
    sic = _sic(st, cand.cik)
    for group, spans in SIC_GROUPS:
        v[f"sic_{group}"] = float(sic is not None and any(lo <= sic <= hi for lo, hi in spans))
    closes = _closes(st, symbol, day)
    raw = sig20_of(closes)
    hist = raw is None
    if hist:
        sig20 = SIG_MISSING
        v["hist_missing"] = 1.0
    else:
        sig20 = min(SIG_CAP, max(SIG_FLOOR, raw))
        v["ln_sig20"] = math.log(sig20 / SIG_SCALE)
        v["r1"] = _clip(math.log(closes[0] / closes[1]), 0.5)
        v["r5"] = _clip(math.log(closes[0] / closes[5]), 1.0)
        v["r20"] = _clip(math.log(closes[0] / closes[19]), 1.5)
    # item 13: the free headline features of an article primary
    if news_primary:
        headline = str(row.get("headline") or "")
        for k, rx in _KW.items():
            v[k] = float(bool(rx.search(headline)))
        k_at = S.parse_iso(str(primary.knowable_at))
        mine = words(headline)
        v["dup72"] = max((jaccard(mine, words(h)) for h in reads.named(symbol, k_at)), default=0.0)
    k_at = S.parse_iso(str(primary.knowable_at))
    local = k_at.astimezone(C.NY)
    if learner.id == "EVL-LRN-O1":
        # item 14 (E11's buckets): overnight 20:00-04:00 ET or any hour of a day that is no session; pre and late of D
        if C.session(st, local.date()) is None or local.time() >= OVERNIGHT_FROM or local.time() < OVERNIGHT_TO:
            v["overnight"] = 1.0
        elif local.date() == day and local.time() < PRE_TO:
            v["pre"] = 1.0
        elif local.date() == day and local.time() < LATE_TO:
            v["late"] = 1.0
        ins = cand.picks.get("EVL-INS-BUY-O1")
        if ins is not None and ins.rank is not None:
            v["ln_ins"] = math.log1p(max(0.0, float(ins.rank)) / INS_SCALE)
    else:
        # item 15: morning (09:00-12:00 ET of D), before (before 09:00 ET of D), dmove from D's '1530' mark (E6)
        d_open = dt.datetime.combine(day, MORNING_FROM, tzinfo=C.NY)
        d_noon = dt.datetime.combine(day, MORNING_TO, tzinfo=C.NY)
        if k_at < d_open:
            v["before"] = 1.0
        elif k_at < d_noon:
            v["morning"] = 1.0
        mark = reads.mark_1530(symbol)
        if mark is None or not prev > 0:
            v["dmove_missing"] = 1.0
        else:
            dmove = _clip(math.log(mark / prev), 0.5)
            v["dmove"], v["abs_dmove"], v["s_x_dmove"] = dmove, abs(dmove), s_num * dmove
    x = [float(v[n]) for n in names]
    if not all(math.isfinite(a) for a in x):
        raise ValueError(f"a feature of {cand.event} is not finite")
    return x, sig20, hist


def held_7(store: Any, learner: P.Program, cik: str, day: dt.date) -> bool:
    """SECTION 1.3 (iii) (PREREG-EVL-1 section 5 as A72 reads it): the learner holds a written, non-skipped intent of
    the issuer ENTERED BEFORE D that exits within the last 5 sessions or later, or ENTERING WITHIN THE 5 SESSIONS AFTER D
    (every one of its id and version, the catch-up's and a late decision's included). Its own intents of D itself are
    neither (they are this decision's picks: a recompute or a catch-up reading them would exclude its own picks)."""
    back = C.previous(store, day, P.ISSUER_GAP_SESSIONS)
    since = back[0].day if back else day
    ahead = C.nth(store, day, P.ISSUER_GAP_SESSIONS + 1)
    until = ahead.day.isoformat() if ahead is not None else "9999-12-31"
    row = store.db.execute("SELECT 1 FROM intents WHERE program=? AND version=? AND cik=? AND status NOT LIKE 'skipped%' "
                           "AND ((entry_day<? AND exit_day>=?) OR (entry_day>? AND entry_day<=?)) LIMIT 1",
                           (learner.id, learner.version, str(cik), day.isoformat(), since.isoformat(), day.isoformat(),
                            until)).fetchone()
    return row is not None


# ------------------------------------------------------------------------------------------------- the training set
def session_days(store: Any, day: dt.date, n: int = LOOKBACK) -> list[dt.date]:
    """The `n` sessions before `day`, oldest first (n(D) - n(s) runs from n down to 1)."""
    return [s.day for s in C.previous(store, day, n)]


def pool_outcomes(store: Any, learner: P.Program, s: dt.date, tau: dt.datetime) -> dict[str, dict[str, Any]]:
    """{cik: the POOL OUTCOME of (s, issuer)} as of tau (section 1.1, section 1.11 item 5): the outcomes row of the first
    pool program, in pool order, holding an intent of the issuer entering at s at the learner's entry and exit auctions,
    `settled`, `tradable` 1, `settled_at` before tau, whose raw entry print (`marks` of s at the entry auction) is at
    most 1.25 x the universe row's previous SIP close (PREREG-EVL-2's limit at entry; a print or a close that cannot be
    read: not a pool outcome)."""
    pool = POOLS[learner.id]
    rows = store.db.execute(
        f"SELECT i.program, i.event, i.cik, i.symbol, i.entry_at, i.exit_at, o.entry_px, o.exit_px, o.bench_entry, "
        f"o.bench_exit, o.settled_at FROM intents i JOIN outcomes o ON o.program=i.program AND o.version=i.version AND "
        f"o.event=i.event WHERE i.entry_day=? AND i.version=1 AND i.program IN ({', '.join('?' * len(pool))}) AND "
        f"o.status='settled' AND o.tradable=1 ORDER BY i.event", (s.isoformat(), *pool)).fetchall()
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if not r["cik"] or r["entry_at"] != learner.entry_at or r["exit_at"] != learner.exit_at:
            continue
        if not _before(r["settled_at"], tau):
            continue
        by.setdefault(str(r["cik"]), []).append(dict(r))
    out: dict[str, dict[str, Any]] = {}
    label = "open" if learner.entry_at == "open" else "close"
    for cik, got in by.items():
        for pid in pool:
            for r in (x for x in got if x["program"] == pid):
                symbol = str(r["symbol"]).upper()
                mark = store.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label=?",
                                        (symbol, s.isoformat(), label)).fetchone()
                uni = store.db.execute("SELECT prev_close FROM universe WHERE day=? AND symbol=?",
                                       (s.isoformat(), symbol)).fetchone()
                try:
                    raw, prev = float(mark["px"]), float(uni["prev_close"])
                except (TypeError, ValueError, IndexError):
                    continue
                if not (math.isfinite(raw) and math.isfinite(prev) and prev > 0) or raw > LIMIT_MULTIPLE * prev:
                    continue
                out[cik] = r
                break
            if cik in out:
                break
    return out


def gross(row: Mapping[str, Any]) -> float | None:
    """E7's GROSS abnormal return of a pool outcome: exit_px / entry_px - bench_exit / bench_entry (the outcomes row's
    prices, adjusted as score.py adjusts them; NO cost column, r or a is read)."""
    try:
        e_in, e_out = float(row["entry_px"]), float(row["exit_px"])
        b_in, b_out = float(row["bench_entry"]), float(row["bench_exit"])
    except (TypeError, ValueError, KeyError):
        return None
    if not (e_in > 0 and b_in > 0 and math.isfinite(e_out) and math.isfinite(b_out)):
        return None
    return e_out / e_in - b_out / b_in


def label(row: Mapping[str, Any], sig20: float) -> float | None:
    a_g = gross(row)
    if a_g is None or not sig20 > 0:
        return None
    return _clip(a_g / sig20, LABEL_CLIP)


def training_session(store: Any, learner: P.Program, s: dt.date, tau: dt.datetime
                     ) -> tuple[list[tuple[str, str, str]], list[tuple[str, list[float], float]]] | None:
    """One earlier session's TRAINING ROWS as of tau: (keys, rows), keys [(cik, pool program, event)] and rows [(cik, x,
    y)], both in CIK order; None when the learner holds no kept candidate of s."""
    cands = store.db.execute("SELECT cik, features, sig20 FROM learner_cands WHERE program=? AND version=? AND day=? AND "
                             "kept=1 AND features IS NOT NULL ORDER BY cik", (learner.id, learner.version,
                                                                              s.isoformat())).fetchall()
    if not cands:
        return None
    outs = pool_outcomes(store, learner, s, tau)
    keys: list[tuple[str, str, str]] = []
    rows: list[tuple[str, list[float], float]] = []
    for c in cands:
        got = outs.get(str(c["cik"]))
        if got is None:
            continue
        keys.append((str(c["cik"]), str(got["program"]), str(got["event"])))
        rows.append((str(c["cik"]), c["features"], c["sig20"], got))      # (parsed only when the cache misses)
    return keys, rows


def keys_sha(day: dt.date, keys: Sequence[tuple[str, str, str]]) -> str:
    return hashlib.sha256(json.dumps([day.isoformat(), [list(k) for k in keys]], separators=(",", ":")).encode()).hexdigest()


def session_stats(rows: Sequence[tuple[str, list[float], float]], width: int) -> dict[str, Any]:
    """WITHIN-SESSION DEMEANING and one session's sums (section 1.5): {n, xx (the upper triangle, row by row), xy}, each
    a `math.fsum` over the session's rows in CIK order; a session with one row adds nothing but its n."""
    n = len(rows)
    if n < 2:
        return {"n": n, "xx": None, "xy": None}
    cols = [[r[1][j] for r in rows] for j in range(width)]
    ys = [r[2] for r in rows]
    mx = [math.fsum(col) / n for col in cols]
    my = math.fsum(ys) / n
    xt = [[v - mx[j] for v in cols[j]] for j in range(width)]
    yt = [v - my for v in ys]
    mul = operator.mul
    xx = [[math.fsum(map(mul, xt[j], xt[k])) for k in range(j, width)] for j in range(width)]
    xy = [math.fsum(map(mul, xt[j], yt)) for j in range(width)]
    return {"n": n, "xx": xx, "xy": xy}


def cholesky(m: Sequence[Sequence[float]]) -> list[list[float]]:
    """The lower Cholesky factor L of a symmetric positive definite `m` (L L' = m), in float64, every inner sum a
    `math.fsum`. Raises ValueError when `m` is not positive definite (the decision fails closed)."""
    n = len(m)
    low = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            acc = math.fsum(low[i][k] * low[j][k] for k in range(j))
            if i == j:
                rest = m[i][i] - acc
                if not (rest > 0 and math.isfinite(rest)):
                    raise ValueError("the ridge matrix is not positive definite")
                low[i][j] = math.sqrt(rest)
            else:
                low[i][j] = (m[i][j] - acc) / low[j][j]
    return low


def solve(low: Sequence[Sequence[float]], rhs: Sequence[float]) -> list[float]:
    """M x = rhs with M = L L' (two triangular solves)."""
    n = len(low)
    y = [0.0] * n
    for i in range(n):
        y[i] = (rhs[i] - math.fsum(low[i][k] * y[k] for k in range(i))) / low[i][i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (y[i] - math.fsum(low[k][i] * x[k] for k in range(i + 1, n))) / low[i][i]
    return x


def fit(stats: Sequence[tuple[float, Mapping[str, Any]]], width: int) -> dict[str, Any]:
    """THE FIT (section 1.5) from the sessions' sums with their weights [(w_s, stats_s)] in day order: {beta, d, n_w}.
    A = fsum_s w_s xx_s, b = fsum_s w_s xy_s, N_w = fsum_s w_s n_s; d_j = sqrt(A_jj / N_w) (a column with d_j < 1e-9:
    d_j = 1, its row, column and b entry 0); M = D^-1 A D^-1 + 8000 I; beta = D^-1 M^-1 D^-1 b by Cholesky."""
    used = [(w, s) for w, s in stats if s.get("xx") is not None]
    n_w = math.fsum(w * float(s["n"]) for w, s in stats)
    if not n_w > 0:
        raise ValueError("no training row")
    a = [[0.0] * width for _ in range(width)]
    for j in range(width):
        for k in range(j, width):
            a[j][k] = a[k][j] = math.fsum(w * s["xx"][j][k - j] for w, s in used)
    b = [math.fsum(w * s["xy"][j] for w, s in used) for j in range(width)]
    d = [0.0] * width
    for j in range(width):
        dj = math.sqrt(a[j][j] / n_w) if a[j][j] > 0 else 0.0
        if dj < D_FLOOR:
            d[j] = 1.0
            for k in range(width):
                a[j][k] = a[k][j] = 0.0
            b[j] = 0.0
        else:
            d[j] = dj
    m = [[a[j][k] / (d[j] * d[k]) + (LAMBDA if j == k else 0.0) for k in range(width)] for j in range(width)]
    low = cholesky(m)
    z = solve(low, [b[j] / d[j] for j in range(width)])
    beta = [z[j] / d[j] for j in range(width)]
    if not all(math.isfinite(v) for v in beta):
        raise ValueError("the fit is not finite")
    return {"beta": beta, "d": d, "n_w": n_w}


def _stats_cached(store: Any, learner: P.Program, s: dt.date, keys: Sequence[tuple[str, str, str]],
                  rows: Sequence[Any], width: int, *, write: bool) -> dict[str, Any]:
    """One session's sums from the cache (section 1.5's key: program, version, session, keys' sha256, code sha), else
    computed from its rows (features as stored at its own tau, the gross label) and kept when `write`."""
    sha = keys_sha(s, keys)
    row = store.db.execute("SELECT stats FROM learner_stats WHERE program=? AND version=? AND day=? AND keys_sha=? AND "
                           "code_sha=?", (learner.id, learner.version, s.isoformat(), sha, CODE_SHA)).fetchone()
    if row is not None:
        return json.loads(row["stats"])
    parsed = []
    for cik, feats, sig20, outcome in rows:
        x = json.loads(feats)["x"]
        y = label(outcome, float(sig20))
        if y is None or len(x) != width:
            raise ValueError(f"a training row of {s} cannot be read ({cik})")
        parsed.append((cik, [float(v) for v in x], y))
    got = session_stats(parsed, width)
    if write:
        store.db.execute("INSERT OR IGNORE INTO learner_stats(program, version, day, keys_sha, code_sha, n, stats) VALUES("
                         "?, ?, ?, ?, ?, ?, ?)", (learner.id, learner.version, s.isoformat(), sha, CODE_SHA, got["n"],
                                                 json.dumps(got, separators=(",", ":"))))
    return got


def training(store: Any, learner: P.Program, day: dt.date, tau: dt.datetime, *, write: bool = True,
             check: Callable[[str], None] | None = None) -> dict[str, Any]:
    """THE TRAINING STATE at tau: {stats [(w_s, sums)], rows, sessions, keys_sha (of every session's ordered keys, in day
    order), by_day {day: n}}."""
    width = len(FEATURES[learner.id])
    days = session_days(store, day)
    stats: list[tuple[float, dict[str, Any]]] = []
    all_keys: list[Any] = []
    by_day: dict[str, int] = {}
    total = 0
    for age_back, s in enumerate(reversed(days), start=1):     # (age 1 = the session before D)
        if check is not None:
            check("the training rows")
        got = training_session(store, learner, s, tau)
        if got is None:
            continue
        keys, rows = got
        if not keys:
            continue
        sums = _stats_cached(store, learner, s, keys, rows, width, write=write)
        w = 2.0 ** (-age_back / HALF_LIFE)
        stats.append((s.toordinal(), w, sums))
        all_keys.append([s.isoformat(), [list(k) for k in keys]])
        by_day[s.isoformat()] = len(keys)
        total += len(keys)
    stats.sort(key=lambda t: t[0])
    all_keys.sort(key=lambda t: t[0])
    sha = hashlib.sha256(json.dumps(all_keys, separators=(",", ":")).encode()).hexdigest()
    return {"stats": [(w, s) for _, w, s in stats], "rows": total, "sessions": len(stats), "keys_sha": sha,
            "by_day": by_day}


# ---------------------------------------------------------------------------------------------------------- the pick
def replay_cost(adv20: float, equity: float | None) -> float:
    """c_i (section 1.6): the replay's round trip as a return (score.py `cost_bp`, entry plus exit)."""
    from . import score as SC

    return (SC.cost_bp(adv20, equity, "entry") + SC.cost_bp(adv20, equity, "exit")) / 1e4


def rank_order(c: Cand) -> tuple[float, float, str]:
    """Section 1.6's order: ahat (higher first), then adv20 (higher first, a missing one as 0), then the event id."""
    return (-(c.ahat if c.ahat is not None else float("-inf")), -c.adv20, c.event)


def predict(cands: list[Cand], beta: Sequence[float], equity: float | None) -> list[float]:
    """e, z and ahat of every kept candidate (section 1.6); returns xbar_D."""
    kept = [c for c in cands if c.kept and c.x is not None]
    width = len(beta)
    xbar = [math.fsum(c.x[j] for c in kept) / len(kept) for j in range(width)] if kept else [0.0] * width
    for c in kept:
        e = math.fsum((c.x[j] - xbar[j]) * beta[j] for j in range(width))
        z = e - replay_cost(c.adv20, equity) / c.sig20
        c.e, c.z, c.ahat = e, z, c.sig20 * z
    return xbar


def choose(cands: list[Cand]) -> list[Cand]:
    """THE PICKS (section 1.6): the eligible candidates with z > 0 in section 1.6's order, the first K."""
    ok = [c for c in cands if c.eligible and c.z is not None and c.z > 0]
    out = sorted(ok, key=rank_order)[:K]
    for i, c in enumerate(out, start=1):
        c.rank = i
    return out


# ------------------------------------------------------------------------------------------------------ a decision
def decided(store: Any, learner: P.Program, day: dt.date) -> Mapping[str, Any] | None:
    """The learner's decision of `day` on record (its fits row), or None."""
    try:
        row = store.db.execute("SELECT * FROM learner_fits WHERE program=? AND version=? AND day=?",
                               (learner.id, learner.version, day.isoformat())).fetchone()
    except Exception:  # noqa: BLE001 - a store without the table holds no decision
        return None
    return None if row is None else dict(row)


def compute(store: Any, learner: P.Program, day: dt.date, *, kind: str, check: Callable[[str], None] | None = None,
            write_cache: bool = True, reconstruct: bool = False) -> dict[str, Any]:
    """ONE DECISION COMPUTED, NOTHING OF IT WRITTEN (but the cache): {tau, bound, cands, picks, fit, training, status,
    why, equity}. `check(where)` raises `Expired` past the part's bound. `reconstruct`: the candidate sets alone
    (section 1.5's reconstruction: no fit, no pick)."""
    tau = tau_of(store, learner, day)
    if tau is None:
        raise LookupError(f"no session {day}")
    check = check or (lambda where: None)
    bound = eligible_by(store, learner, day)
    out: dict[str, Any] = {"tau": tau, "bound": bound, "status": "ok", "why": "", "picks": [], "fit": None,
                           "training": None, "kind": kind}
    cands, counts = candidates(store, learner, day, tau, bound)
    out["counts"] = counts
    check("the features")
    equity = equity_prev(store, day)
    out["equity"] = equity
    reads = Reads(store, learner, day, tau)
    registered = None if reconstruct else learner.registered_at
    for c in cands:
        c.kept = tradable(c.uni.get("prev_close"), equity)
        if not c.kept:
            continue
        c.x, c.sig20, c.hist = features(reads, c)
        if registered is not None and S.parse_iso(str(c.primary.knowable_at)) > registered:
            c.eligible = not held_7(store, learner, c.cik, day)
    out["cands"] = cands
    if reconstruct:
        out["why"] = "reconstructed (section 1.5): the candidate set alone"
        return out
    if equity is None:
        out.update(status="closed", why="no E_prev on record: no candidate is TRADABLE (fail closed)")
        return out
    check("the training rows")
    train = training(store, learner, day, tau, write=write_cache, check=check)
    out["training"] = train
    if train["rows"] < WARM_ROWS or train["sessions"] < WARM_SESSIONS:
        out["why"] = (f"warm-up: {train['rows']} training rows from {train['sessions']} sessions (needs {WARM_ROWS} "
                      f"from {WARM_SESSIONS})")
        out["status"] = "warmup"
        return out
    check("the fit")
    width = len(FEATURES[learner.id])
    try:
        got = fit(train["stats"], width)
    except ValueError as exc:
        out.update(status="closed", why=f"fail closed: {exc}")
        return out
    out["fit"] = got
    xbar = predict(cands, got["beta"], equity)
    got["xbar"] = xbar
    out["picks"] = choose(cands)
    return out


def _write(store: Any, learner: P.Program, day: dt.date, got: Mapping[str, Any], *, kind: str, receipt: str | None,
           receipt_id: int | None, started: dt.datetime, now: dt.datetime) -> dict[str, Any]:
    """THE DECISION WRITTEN ONCE, in one transaction: its candidates (`learner_cands`), its fits row and its picks as
    intents (`intents.rank_key` = ahat; a catch-up's and a late decision's say so in `why`). A decision already on
    record is never written again (returns {"known": True})."""
    tau = got["tau"]
    picks = list(got.get("picks") or [])
    fitted = got.get("fit") or {}
    train = got.get("training") or {}
    why_intent = None if kind == "live" else (
        f"{kind} (PREREG-EVL-7 section 1.7: training state and a reported shadow, never judged, never traded)")
    with store.tx() as db:
        ensure_in_tx(db)
        if db.execute("SELECT 1 FROM learner_fits WHERE program=? AND version=? AND day=?",
                      (learner.id, learner.version, day.isoformat())).fetchone() is not None:
            return {"known": True}
        for c in got.get("cands") or []:
            feats = None if c.x is None else json.dumps({"x": c.x, "hist": int(c.hist)}, separators=(",", ":"))
            db.execute("INSERT OR IGNORE INTO learner_cands(program, version, day, cik, event, symbol, families, kept, "
                       "eligible, features, sig20, adv20, prev_close, knowable_at, e, z, ahat, picked, rank, kind) VALUES("
                       "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (learner.id, learner.version, day.isoformat(), c.cik, c.event,
                        str(c.uni.get("symbol") or c.primary.symbol).upper(), json.dumps(c.families), int(c.kept),
                        int(c.eligible), feats, c.sig20 if c.x is not None else None, c.adv20,
                        _float(c.uni.get("prev_close")), str(c.primary.knowable_at), c.e, c.z, c.ahat,
                        int(c.rank is not None), c.rank, kind))
        cands = [P.Candidate(c.event, c.cik, str(c.uni.get("symbol") or c.primary.symbol).upper(),
                             S.parse_iso(str(c.primary.knowable_at)), c.ahat, None, {}) for c in picks]
        written = P.write_intents(store, learner, day, cands, decided_at=tau, why=why_intent) if cands else {}
        db.execute("INSERT INTO learner_fits(program, version, day, tau, kind, receipt, receipt_id, status, why, n_cands, "
                   "n_kept, n_rows, n_sessions, n_picks, keys_sha, code_sha, beta, d, xbar, eligible_by, train_last, "
                   "started_at, finished_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (learner.id, learner.version, day.isoformat(), S.iso(tau), kind, receipt, receipt_id, got["status"],
                    str(got.get("why") or "")[:400], len(got.get("cands") or []),
                    sum(1 for c in got.get("cands") or [] if c.kept), train.get("rows"), train.get("sessions"),
                    len(picks), train.get("keys_sha"), CODE_SHA,
                    None if not fitted else json.dumps(fitted["beta"]), None if not fitted else json.dumps(fitted["d"]),
                    None if not fitted else json.dumps(fitted.get("xbar")),
                    None if got.get("bound") is None else S.iso(got["bound"]),
                    max(train.get("by_day") or {}, default=None), S.iso(started), S.iso(now)))
    return {"kind": kind, "status": got["status"], "picks": len(picks), "candidates": len(got.get("cands") or []),
            "rows": train.get("rows"), "intents": written}


def ensure_in_tx(db: Any) -> None:
    """The learner's tables inside an open transaction (CREATE TABLE IF NOT EXISTS, one statement each)."""
    for stmt in SCHEMA.split(";"):
        if stmt.strip():
            db.execute(stmt)


def _float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def decide(store: Any, learner: P.Program, day: dt.date, *, kind: str, now: Callable[[], dt.datetime] = S.utc_now,
           receipt: str | None = None, receipt_id: int | None = None, check: Callable[[str], None] | None = None,
           before_write: Callable[[], None] | None = None) -> dict[str, Any]:
    """ONE DECISION OF `learner` FOR ENTRY SESSION `day`, computed exactly as of its tau and written once (`compute`,
    `_write`). A decision on record is never decided again. `check` raises `Expired` past the part's bound (nothing is
    written); `before_write` runs just before the write (the live part's last bound check)."""
    if kind not in KINDS:
        raise ValueError(f"no learner decision kind {kind!r}")
    if not P.registers_7() or P.BY_KEY.get(learner.key) is None:
        return {"skipped": "PREREG-EVL-7 registers nothing (REGISTERED_AT_7 unpinned or not after REGISTERED_AT_6)"}
    ensure(store.db)
    if decided(store, learner, day) is not None:
        return {"known": True}
    started = now()
    got = compute(store, learner, day, kind=kind, check=check, reconstruct=(kind == "reconstruct"))
    if kind == "reconstruct":
        got["status"] = "reconstructed"
    if before_write is not None:
        before_write()
    out = _write(store, learner, day, got, kind=kind, receipt=receipt, receipt_id=receipt_id, started=started, now=now())
    if not out.get("known") and kind != "reconstruct":
        try:        # (the recompute's fingerprints, kept at the decision; a failure here is never the decision's)
            remember_inputs(store, learner, day)
        except Exception:  # noqa: BLE001
            pass
    return out


# ------------------------------------------------------------------------------------------- the live part (run.py)
def live_part(ctx: Any, learner: P.Program, day: dt.date, *, receipt_id: int | None, budget: float | None = None
              ) -> dict[str, Any]:
    """THE LEARNER'S PART OF THE HOUSE'S DECISION (section 1.7's ISOLATION), run by league/events/run.py right after the
    House's decision receipt of the auction finished (so no earlier row waits on it), only for the FIRST such receipt
    of the session (E5's bound is its finish) and only when that decision was live: the decision under its own bound
    (`BOUND_S`, from now, never past the task's bound less FINISH_S), kind `live`, recorded under that receipt's id.
    EVL-LRN-ON's candidates' '1530' marks are read first, in the close decision's batched requests (run.py
    `_marks_1530`, E6). NEVER RAISES: a failure or an expiry writes nothing but meta `PART_KEY` ({status, why, at}),
    and that auction is decided later by itself (`catchup`, kind `late`), in shadow only."""
    from . import run as R

    st = ctx.store
    mono = getattr(ctx, "mono", None) or time.monotonic
    secs = BOUND_S[learner.entry_at] if budget is None else float(budget)
    until = mono() + secs
    deadline = getattr(ctx, "deadline", None)
    if deadline is not None:
        until = min(until, float(deadline) - FINISH_S)
    key = PART_KEY.format(program=learner.id, version=learner.version, day=day.isoformat())

    def check(where: str) -> None:
        if mono() >= until:
            raise Expired(f"the learner part ran past its own time bound before {where}")
    try:
        first = house_receipt(st, learner, day)
        if first is None or receipt_id is None or int(first["id"]) != int(receipt_id):
            return {"skipped": "not the first finished House decision of the auction"}
        ensure(st.db)
        if decided(st, learner, day) is not None:
            return {"known": True}
        check("its reads")
        if learner.entry_at == "close":
            tau = tau_of(st, learner, day)
            bound = eligible_by(st, learner, day)
            cands, _ = candidates(st, learner, day, tau, bound) if tau is not None else ([], {})
            symbols = sorted({str(c.uni.get("symbol") or "").upper() for c in cands if c.uni.get("symbol")})
            if symbols:
                R._marks_1530(R.bounded(ctx, until), symbols, day)
        out = decide(st, learner, day, kind="live", now=ctx.now, receipt=f"decide-{learner.entry_at}:{day.isoformat()}",
                     receipt_id=int(receipt_id), check=check, before_write=lambda: check("its write"))
        return out
    except (Expired, R.PartDeadline) as exc:
        st.set_meta(key, json.dumps({"status": "expired", "why": str(exc)[:300], "at": S.iso(ctx.now())},
                                    sort_keys=True))
        return {"expired": str(exc)[:300]}
    except Exception as exc:  # noqa: BLE001 - the part's failure is its own (section 1.7's ISOLATION)
        try:
            st.set_meta(key, json.dumps({"status": "failed", "why": f"{type(exc).__name__}: {str(exc)[:240]}",
                                         "at": S.iso(ctx.now())}, sort_keys=True))
        except Exception:  # noqa: BLE001 - the record of a failure never fails the decision
            pass
        return {"failed": f"{type(exc).__name__}: {str(exc)[:240]}"}


# ------------------------------------------------------------------------------------------ the catch-up (house.py)
def first_live(store: Any, learner: P.Program) -> dt.date | None:
    """The first entry session the House's release carrying this code decided live for the learner (section 1.7: the
    record and real money start there), None before it."""
    try:
        row = store.db.execute("SELECT MIN(day) FROM learner_fits WHERE program=? AND version=? AND kind='live'",
                               (learner.id, learner.version)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    return None if row is None or row[0] is None else dt.date.fromisoformat(str(row[0]))


def due(store: Any, now: dt.datetime, *, settle_s: float = 60.0) -> list[tuple[str, P.Program, dt.date]]:
    """WHAT THE LEARNERS STILL OWE, oldest first: ("reconstruct", L, s) for every session from PREREG-EVL-1's
    registration whose tau is at or before REGISTERED_AT_7 (once each, before anything else of L), then ("catchup" or
    "late", L, D) for every session whose tau is after REGISTERED_AT_7 with no decision on record, whose House decision
    of the auction has finished, and whose live part had its chance (its first receipt finished more than the part's
    bound + `settle_s` ago, or that decision was not live): before the release's first live decision a CATCH-UP (E4),
    after it a LATE decision of a part that failed or expired."""
    out: list[tuple[str, P.Program, dt.date]] = []
    if not P.registers_7():
        return out
    try:
        ensure(store.db)
    except Exception:  # noqa: BLE001 - a store that cannot take the tables owes nothing yet
        return out
    reg = S.parse_iso(str(P.REGISTERED_AT_7))
    start = P.registered().astimezone(C.NY).date()
    today = now.astimezone(C.NY).date()
    for learner in P.learners():
        have = {str(r[0]) for r in store.db.execute("SELECT day FROM learner_fits WHERE program=? AND version=?",
                                                    (learner.id, learner.version))}
        live0 = first_live(store, learner)
        for s in C.sessions(store, start, today):
            tau = tau_of(store, learner, s.day)
            if tau is None or tau > now or s.day.isoformat() in have:
                continue
            if tau <= reg:
                out.append(("reconstruct", learner, s.day))
                continue
            first = house_receipt(store, learner, s.day)
            if first is None:
                continue
            try:
                finished = S.parse_iso(str(first["finished_at"]))
            except (TypeError, ValueError):
                continue
            live = _live_receipt(store, learner, s.day, first)
            if live and now < finished + dt.timedelta(seconds=BOUND_S[learner.entry_at] + settle_s):
                continue
            out.append(("catchup" if live0 is None or s.day < live0 else "late", learner, s.day))
    order = {"reconstruct": 0, "catchup": 1, "late": 1}
    return sorted(out, key=lambda t: (order[t[0]], t[2], t[1].id))


def _live_receipt(store: Any, learner: P.Program, day: dt.date, first: Mapping[str, Any]) -> bool:
    """Whether the House's first finished decision of the auction was LIVE (league/events/run.py `live_run`: started
    within LIVE_WITHIN of its scheduled time), so its learner part ran in it."""
    from . import run as R

    tau = tau_of(store, learner, day)
    try:
        started = S.parse_iso(str(first["started_at"]))
    except (TypeError, ValueError):
        return False
    return tau is not None and R.live_run(tau, started)


def catchup(store: Any, now: Callable[[], dt.datetime] = S.utc_now, *, check: Callable[[str], None] | None = None,
            limit: int | None = None) -> dict[str, Any]:
    """THE LEARNERS' OWN DECISIONS (section 1.7): every `due` one, oldest first, exactly as of its tau, each under its
    own receipt (`RECEIPT` kind for a catch-up or a late decision; none for a reconstruction), shadow only. A decision
    that raises is tried again at the next run, CATCHUP_TRIES times in all, then written closed. Returns counts."""
    counts: dict[str, Any] = {"decided": 0, "failed": [], "reconstruct": 0, "catchup": 0, "late": 0}
    for i, (kind, learner, day) in enumerate(due(store, now())):
        if limit is not None and i >= limit:
            break
        if check is not None:
            check(f"the learner's {kind} of {day}")
        job = f"{RECEIPT[learner.entry_at]}:{day.isoformat()}"
        rid = None if kind == "reconstruct" else store.start_receipt(job, now=now())
        try:
            got = decide(store, learner, day, kind=kind, now=now, receipt=None if rid is None else job, receipt_id=rid)
        except Expired:
            raise
        except Exception as exc:  # noqa: BLE001 - tried again; written closed after CATCHUP_TRIES
            why = f"{type(exc).__name__}: {str(exc)[:200]}"
            tries_key = f"evl7:tries:{learner.id}:{learner.version}:{day.isoformat()}"
            tries = int(store.meta(tries_key) or 0) + 1
            store.set_meta(tries_key, str(tries))
            if rid is not None:
                store.finish_receipt(rid, "failed", {"program": learner.id, "error": why}, now=now())
            if tries >= CATCHUP_TRIES:
                _write_closed(store, learner, day, kind=kind, why=f"failed {tries} times: {why}", now=now())
            counts["failed"].append(f"{learner.id} {day}: {why}")
            continue
        if rid is not None:
            store.finish_receipt(rid, "ok", {"program": learner.id, "kind": kind, **{k: v for k, v in got.items()
                                                                                    if k != "intents"}}, now=now())
        counts["decided"] += 1
        counts[kind] += 1
    return counts


def _write_closed(store: Any, learner: P.Program, day: dt.date, *, kind: str, why: str, now: dt.datetime) -> None:
    tau = tau_of(store, learner, day)
    with store.tx() as db:
        ensure_in_tx(db)
        db.execute("INSERT OR IGNORE INTO learner_fits(program, version, day, tau, kind, status, why, n_picks, code_sha, "
                   "started_at, finished_at) VALUES(?, ?, ?, ?, ?, 'closed', ?, 0, ?, ?, ?)",
                   (learner.id, learner.version, day.isoformat(), S.iso(tau) if tau else "", kind, why[:400], CODE_SHA,
                    S.iso(now), S.iso(now)))


# ---------------------------------------------------------------------------------------- the nightly recompute
def inputs_sha(store: Any, learner: P.Program, day: dt.date, tau: dt.datetime) -> dict[str, str]:
    """THE FINGERPRINTS OF THE STORED INPUTS A DECISION READS THAT MAY CHANGE AFTER ITS TAU (check 2's minor 10 (2)),
    {name: sha256}: the pool programs' and the learner's own intents around D (one position per issuer: only whether
    each is skipped, so a settlement moves nothing), the live eligibility results and universe rows of D within E5's
    bound, the bars of D's candidates' symbols before D (read as stored whatever their write time), their SIC codes,
    EVL-LRN-ON's '1530' marks of D, and the earlier sessions' candidate sets the training reads (a late decision of an
    earlier session written after D's). The nightly recompute compares beta and the picks only where none moved."""
    pool = POOLS[learner.id]
    back = C.previous(store, day, P.ISSUER_GAP_SESSIONS + 1)
    lo = back[0].day.isoformat() if back else day.isoformat()
    ahead = C.nth(store, day, P.ISSUER_GAP_SESSIONS + 2)
    hi = ahead.day.isoformat() if ahead is not None else "9999-12-31"
    bound = eligible_by(store, learner, day)
    bound_s = S.iso(bound) if bound is not None else ""

    def sha(rows: Iterable[Any]) -> str:
        return hashlib.sha256(json.dumps([list(r) for r in rows], default=str, separators=(",", ":")).encode()).hexdigest()
    ph = ", ".join("?" * len(pool))
    held = "CASE WHEN status LIKE 'skipped%' THEN 'skipped' ELSE 'held' END"
    intents = store.db.execute(f"SELECT program, event, cik, entry_day, exit_day, {held} FROM intents WHERE program IN "
                               f"({ph}) AND version=1 AND exit_day>=? AND entry_day<=? ORDER BY program, event",
                               (*pool, lo, hi)).fetchall()
    own = store.db.execute(f"SELECT event, cik, entry_day, exit_day, {held} FROM intents WHERE program=? AND version=? AND "
                           "exit_day>=? AND entry_day<=? AND entry_day<>? ORDER BY event",
                           (learner.id, learner.version, lo, hi, day.isoformat())).fetchall()
    elig = store.db.execute("SELECT cik, rule, eligible, symbol, decided_at FROM eligibility WHERE day=? AND decided_at<=? "
                            "ORDER BY cik, rule", (day.isoformat(), bound_s)).fetchall()
    universe = store.db.execute("SELECT u.* FROM universe u JOIN eligibility e ON e.day=u.day AND e.cik=u.cik AND "
                                "e.symbol=u.symbol WHERE u.day=? AND e.rule='live' AND e.eligible=1 AND e.decided_at<=? "
                                "ORDER BY u.symbol", (day.isoformat(), bound_s)).fetchall()
    symbols = sorted({str(r["symbol"]) for r in universe})
    bars: list[Any] = []
    first = (day - dt.timedelta(days=45)).isoformat()
    for k in range(0, len(symbols), 400):
        part = symbols[k:k + 400]
        bars += store.db.execute(f"SELECT symbol, day, c FROM bars WHERE adj='raw' AND day<? AND day>=? AND symbol IN "
                                 f"({', '.join('?' * len(part))}) ORDER BY symbol, day", (day.isoformat(), first, *part)
                                 ).fetchall()
    ciks = sorted({str(r["cik"]) for r in universe})
    sic: list[Any] = []
    for k in range(0, len(ciks), 400):
        part = ciks[k:k + 400]
        sic += store.db.execute(f"SELECT cik, sic FROM cik_info WHERE cik IN ({', '.join('?' * len(part))}) ORDER BY cik",
                                part).fetchall()
    marks = store.db.execute("SELECT symbol, px, t FROM marks WHERE day=? AND label='1530' ORDER BY symbol",
                             (day.isoformat(),)).fetchall() if learner.entry_at == "close" else []
    sets = store.db.execute("SELECT day, COUNT(*), SUM(kept) FROM learner_cands WHERE program=? AND version=? AND day<? AND "
                            "day>=? GROUP BY day ORDER BY day", (learner.id, learner.version, day.isoformat(),
                                                                 (day - dt.timedelta(days=400)).isoformat())).fetchall()
    return {"intents": sha(intents), "own": sha(own), "eligibility": sha(elig), "universe": sha(universe),
            "bars": sha(bars), "sic": sha(sic), "marks": sha(marks), "sets": sha(sets)}


INPUTS_KEY = "evl7:inputs:{program}:{version}:{day}"


def remember_inputs(store: Any, learner: P.Program, day: dt.date) -> None:
    """The inputs' fingerprints at the decision (`inputs_sha`), kept for the nightly recompute (meta `INPUTS_KEY`)."""
    tau = tau_of(store, learner, day)
    if tau is None:
        return
    key = INPUTS_KEY.format(program=learner.id, version=learner.version, day=day.isoformat())
    if store.meta(key) is None:
        store.set_meta(key, json.dumps(inputs_sha(store, learner, day, tau), sort_keys=True))


def recompute(store: Any, day: dt.date, now: Callable[[], dt.datetime] = S.utc_now) -> dict[str, Any]:
    """THE NIGHTLY RECOMPUTE (section 1.8): each learner's decision of `day` on record decided again in memory exactly as
    of its tau (no write but the cache's, which is keyed by its inputs), and beta and the picks compared ONLY where the
    stored inputs are unchanged since the decision (`inputs_sha` against those kept at the decision); written to meta
    `RECOMPUTE_KEY` ({program@vN: {status: match | mismatch | changed | none, cause}}); a mismatch is the alarm's
    (league/ops/evl_learner.py). A decision is never rewritten."""
    out: dict[str, Any] = {}
    for learner in P.learners():
        key = f"{learner.id}@v{learner.version}"
        rec = decided(store, learner, day)
        if rec is None or rec.get("kind") == "reconstruct":
            out[key] = {"status": "none"}
            continue
        tau = tau_of(store, learner, day)
        kept_raw = store.meta(INPUTS_KEY.format(program=learner.id, version=learner.version, day=day.isoformat()))
        now_inputs = inputs_sha(store, learner, day, tau)
        changed = None
        if kept_raw is None:
            changed = ["no fingerprint kept at the decision"]
        else:
            kept = json.loads(kept_raw)
            changed = sorted(k for k in now_inputs if kept.get(k) != now_inputs[k])
        try:
            got = compute(store, learner, day, kind=str(rec["kind"]), write_cache=False)
        except Exception as exc:  # noqa: BLE001 - said, never raised
            out[key] = {"status": "mismatch", "cause": f"the recompute raised {type(exc).__name__}: {str(exc)[:160]}"}
            continue
        keys_now = (got.get("training") or {}).get("keys_sha")
        if rec.get("keys_sha") and keys_now and rec["keys_sha"] != keys_now:
            changed = sorted(set(changed or []) | {"training keys"})
        was = [str(r[0]) for r in store.db.execute("SELECT event FROM learner_cands WHERE program=? AND version=? AND "
                                                   "day=? AND picked=1 ORDER BY rank", (learner.id, learner.version,
                                                                                         day.isoformat()))]
        now_picks = [c.event for c in got.get("picks") or []]
        beta_was = json.loads(rec["beta"]) if rec.get("beta") else None
        beta_now = (got.get("fit") or {}).get("beta")
        same = was == now_picks and beta_was == beta_now
        if changed:
            out[key] = {"status": "changed", "cause": "stored inputs changed since the decision: " + ", ".join(changed),
                        "same": same}
        elif same:
            out[key] = {"status": "match"}
        else:
            cause = []
            if was != now_picks:
                cause.append(f"picks {was} != {now_picks}")
            if beta_was != beta_now:
                cause.append("beta differs")
            out[key] = {"status": "mismatch", "cause": "; ".join(cause)[:300]}
    store.set_meta(RECOMPUTE_KEY.format(day=day.isoformat()), json.dumps(out | {"at": S.iso(now())}, sort_keys=True))
    return out


# --------------------------------------------------------------------------------------------- the real money read
def live_picks(lane: Any, learner: P.Program, day: dt.date) -> list[dict[str, Any]] | None:
    """THE LEARNER'S LIVE PICKS OF `day` for real money (section 1.9): its decision of kind `live` (the House's own,
    under its bound), its picked candidates in rank order with what the book needs; None when no live decision of
    `day` is on record (the auction is not traded for it: a part that did not finish, or before the release)."""
    try:
        rec = lane.db.execute("SELECT kind, status FROM learner_fits WHERE program=? AND version=? AND day=?",
                              (learner.id, learner.version, day.isoformat())).fetchone()
    except Exception:  # noqa: BLE001 - no table: no decision
        return None
    if rec is None or str(rec["kind"]) != "live":
        return None
    rows = lane.db.execute("SELECT c.cik, c.event, c.symbol, c.adv20, c.prev_close, c.knowable_at, c.rank, i.status FROM "
                           "learner_cands c JOIN intents i ON i.program=c.program AND i.version=c.version AND "
                           "i.event=c.event WHERE c.program=? AND c.version=? AND c.day=? AND c.picked=1 ORDER BY c.rank",
                           (learner.id, learner.version, day.isoformat())).fetchall()
    return [dict(r) for r in rows if not str(r["status"]).startswith("skipped")]


# ----------------------------------------------------------------------------------------- the report's lines
def report_lines(store: Any, day: dt.date) -> list[dict[str, Any]]:
    """THE REPORT'S LEARNER LINES (section 3.2; the task's item 5): per learner in force, the decision of `day` (its
    kind, status, candidates, kept, picks, training rows and sessions, warm-up) and whether its part failed or expired.
    COUNTS ONLY: no beta, d, xbar, e, z, ahat or anything fitted reaches a report, the site or births."""
    out = []
    for learner in P.learners():
        rec = decided(store, learner, day)
        part = store.meta(PART_KEY.format(program=learner.id, version=learner.version, day=day.isoformat()))
        line: dict[str, Any] = {"program": learner.id, "version": learner.version, "day": day.isoformat()}
        if rec is not None:
            line |= {"kind": rec["kind"], "status": rec["status"], "candidates": rec.get("n_cands"),
                     "kept": rec.get("n_kept"), "picks": rec.get("n_picks"), "training_rows": rec.get("n_rows"),
                     "training_sessions": rec.get("n_sessions"),
                     "warm": bool((rec.get("n_rows") or 0) >= WARM_ROWS and (rec.get("n_sessions") or 0) >= WARM_SESSIONS)}
        if part is not None:
            try:
                line["part"] = {k: v for k, v in json.loads(part).items() if k in ("status", "at")}
            except ValueError:
                line["part"] = {"status": "unreadable"}
        out.append(line)
    return out


def render_lines(lines: Sequence[Mapping[str, Any]]) -> list[str]:
    out = []
    for x in lines:
        if "kind" not in x:
            text = f"{x['program']} v{x['version']}: no decision of {x['day']}"
        else:
            text = (f"{x['program']} v{x['version']}: {x['kind']} {x['status']}, candidates {x.get('candidates')}, kept "
                    f"{x.get('kept')}, picks {x.get('picks')}, training rows {x.get('training_rows')} from "
                    f"{x.get('training_sessions')} sessions{'' if x.get('warm') else ' (warm-up)'}")
        if x.get("part"):
            text += f"; part {x['part'].get('status')}"
        out.append(text)
    return out


__all__ = ["POOLS", "K", "LAMBDA", "HALF_LIFE", "LOOKBACK", "WARM_ROWS", "WARM_SESSIONS", "BOUND_S", "RECEIPT", "KINDS",
           "SPEC_SHA", "STOP", "KEYWORDS", "words", "jaccard", "FEATURES", "feature_names", "CODE_SHA", "SCHEMA",
           "TABLES", "ensure", "Expired", "Cand", "AsOf", "tau_of", "house_receipt", "eligible_by", "equity_prev",
           "tradable", "pool_programs", "candidates", "sig20_of", "features", "held_7", "pool_outcomes", "gross", "label",
           "training", "session_stats", "cholesky", "solve", "fit", "replay_cost", "predict", "choose", "decided",
           "compute", "decide", "live_part", "due", "catchup", "first_live", "recompute", "inputs_sha",
           "remember_inputs", "live_picks", "report_lines", "render_lines", "PART_KEY", "RECOMPUTE_KEY", "INPUTS_KEY"]
