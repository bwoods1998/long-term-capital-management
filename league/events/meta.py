"""PREREG-EVL-8 PART B: THE META-LEARNERS EVL-META-O1 AND EVL-META-ON (docs/prereg/PREREG-EVL-8.md section 7 once
frozen; until then goal-2026-10-19/evl8/PREREG-EVL-8.md, the final text of the fix round), a port of the META
designer's reference spec (goal-2026-10-19/evl8/meta/meta_spec.py: `grid_rules`, `features`, `rules_of`,
`session_stats`, `state`, `posterior`, `walk`, word for word). Standard library only. NOTHING HERE DECIDES, WRITES OR
IS CHARGED while league/events/programs.py `REGISTERED_AT_8` is None.

MRL-EB, THE EMPIRICAL-BAYES LOWER-CONFIDENCE RULE WALK (section 7.4-7.6): each decision of (D, X) at its tau
(09:15 ET for EVL-META-O1, the close decision time for EVL-META-ON)
1. reads its MEMBERS BY THE MEMBERS RULE (section 7.2), FIXED BY STORED TIMES ALONE, so the live decision and every
   catch-up read the same members whenever they run (`source_picks`): each SOURCE (every program version registered
   before the decision with hold 1 and X's entry and exit auctions but EVL-META-*, PX's placebos and the POOL records)
   gives members only through ITS LIVE DECISION of (D, X): a source decided in the lane's runs only when THE LANE'S
   FIRST FINISHED DECISION of (D, X) names it, by its REAL-MONEY READING of D at tau (league/events/book.py `picks`
   over ELIGIBLE TO PICK's rows, with the REACT rows' reaction and the gap read from THE MARKS: `AsOf`); a
   PREREG-EVL-7 learner by its live decision's intents; this file's PX seats and controls by the names THE LIVE PX RUN
   of (D, X) selected (league/events/px.py `live_selections`). Never an hourly re-decision's intents, never a
   by-itself later decision's, never a `decide-px` catch-up's. One member an issuer: its event the earliest knowable
   (ties: the lowest id), its tags the sources giving one;
2. writes each member ONCE (`mrl_pool`): its event, tags, binary FEATURES (section 7.3, from rows stored before tau
   and THE MARKS), its PX record rules (`x:<record>`: part A's O1 or ON records that select the issuer on D, from the
   px_features rows of THE LIVE PX RUN of (D, X) only, `px.live_features`; none without one), and whether it is
   ELIGIBLE TO PICK (the lane's live result decided at or before the lane's first finish and never after the entry
   auction, or px_universe's live row for a member whose only sources are PX rows; knowable after REGISTERED_AT_8;
   TRADABLE; not held within 5 sessions: A72);
3. reads THE STATE as of its state time sigma (09:00 ET, or the close - 30 minutes): every entered session from Oct
   20, 2026, its members as written at its own decision and their OUTCOMES (F9: the settled outcome, under the first
   of its tags in programs.py's order that holds one, of that tag's intent of the issuer at the member's auctions,
   PREREG-EVL-2's LIMIT AT ENTRY applied to every member, TRADABLE only) settled before sigma; a session enters once
   every member is settled or terminal, or 3 sessions after its exit (a member still unsettled then counts a = -0.30);
4. walks the qualified sub-rules (NB >= MINB, -cbar + LCB > 0) in descending LCB (ties: the larger NB, then the id),
   each giving its eligible members by adv20 then event id, until K = 16 are taken; nothing before the state holds more
   than WARM = 10 entered sessions (the port calls the walk with session_index = the entered sessions), none before the
   first decision after REGISTERED_AT_8.

WHAT IS WRITTEN (F8): each pick is an intent with rank_key = K + 1 - its walk position and why "mrl"; NO LCB, sub-rule id
or figure goes into an intent, a receipt or any table the report, the site, births or the captain read. The walk (each
pick's position, the sub-rule that gave it as h = sha256("EVL8-MRL|" + id)[:16], its LCB, NB and the qualified count)
is in `mrl_walk` only, the state in `mrl_stats` and `mrl_state`, the members in `mrl_pool`: machine-only, every mrl_*
table on births' FACTS_DENY and the report's deny list (`TABLES`).

ONE DECISION, WRITTEN ONCE (`mrl_decisions`): its kind `live` (the House's own, in its own run at section 4.6's
time: EVL-META-O1's part of the open run after PX-GAP-O1's, receipt `decide-open-meta8:<D>`; EVL-META-ON's
`decide-close-meta8:<D>`, the first task on the lane's close receipt) or `catchup` (`decide-meta:<open|close>:<D>`: a
session before the release, or a live part that did not run or finish, decided later by itself exactly as of its own
tau and sigma, oldest first), never decided again. Only a live decision is traded or judged; every receipt records
the code's sha (`CODE_SHA`)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import programs as P
from . import store as S
from . import verdicts as V

# ---------------------------------------------------------------------------------------------- registered constants
K = 16                 # picks a decision at most
H = 60.0               # half-life of a session's weight, in sessions entered
TAU = 0.0030           # prior sd of a sub-rule's relative edge (after cost, per event)
SF = 0.0020            # block-noise floor of a relative block
Z = 3.0                # the lower confidence bound's multiplier
HURDLE = 0.0           # a sub-rule qualifies when -cbar + LCB > HURDLE
MINB = 3               # settled blocks a sub-rule needs to be awake
WARM = 10              # no pick while the state holds WARM entered sessions or fewer
WINSOR = 0.10          # within-session deviations clipped at +-10% for the variance estimate
VAR_FLOOR = 0.015 ** 2
IMPUTE_AFTER = 3       # sessions after a session's scheduled exit before its unsettled members are imputed
IMPUTE_A = -0.30       # ... at a = -30%, replaced by the settled value once settled
ISSUER_GAP = 5         # PREREG-EVL-1 section 5's one position per issuer per program (A72)
FAMILY_CAP = 1535      # section 7.3: never above the 1,535 sub-rules the calibration measured
LIMIT_MULTIPLE = 1.25  # PREREG-EVL-2's LIMIT AT ENTRY (F9)
TRADABLE_SHARE = 0.10  # TRADABLE at the decision: 1.25 x prev_close <= 10% of the equity at P's close
STATE_FROM = dt.date(2026, 10, 20)     # section 7.4: the lane's first full session
COV_WINDOW = dt.timedelta(hours=72)
CLOSES = 20
#: The two meta-learners and their auctions.
PROGRAM_OF = {"o1": "EVL-META-O1", "on": "EVL-META-ON"}
POOL_OF = {"EVL-META-O1": "EVL-META-O1-POOL", "EVL-META-ON": "EVL-META-ON-POOL"}
#: Receipts: the live parts and a catch-up.
JOB_LIVE = {"o1": "decide-open-meta8", "on": "decide-close-meta8"}
JOB_CATCHUP = "decide-meta"
JOB_PREPASS = "prepass-meta"
#: Section 4.6: the state times and the parts' bounds.
SIGMA_OPEN = dt.time(9, 0)
SIGMA_CLOSE_BEFORE = dt.timedelta(minutes=30)
PREPASS_BUDGET = 120.0
META_CLOSE_BOUND = 15.0
META_CLOSE_UNTIL = dt.timedelta(minutes=11, seconds=20)          # never past close - 11:20 (15:48:40)
WHY = "mrl"
#: The code's sha (each decision's receipt and row record it: a catch-up's code is pinned by it).
CODE_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

SCHEMA = """
CREATE TABLE IF NOT EXISTS mrl_decisions(program TEXT NOT NULL, version INTEGER NOT NULL, day TEXT NOT NULL,
  kind TEXT NOT NULL, receipt INTEGER, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, code_sha TEXT,
  members INTEGER, eligible INTEGER, picks INTEGER, PRIMARY KEY(program, version, day));
CREATE TABLE IF NOT EXISTS mrl_pool(program TEXT NOT NULL, version INTEGER NOT NULL, day TEXT NOT NULL, cik TEXT NOT NULL,
  symbol TEXT NOT NULL, event TEXT NOT NULL, knowable_at TEXT, tags TEXT NOT NULL, features TEXT NOT NULL,
  xrules TEXT NOT NULL, eligible INTEGER NOT NULL, adv20 REAL, prev_close REAL, cost_rt REAL,
  PRIMARY KEY(program, version, day, cik));
CREATE TABLE IF NOT EXISTS mrl_state(program TEXT NOT NULL, version INTEGER NOT NULL, day TEXT NOT NULL,
  sigma TEXT NOT NULL, run TEXT NOT NULL, entered INTEGER NOT NULL, imputed INTEGER NOT NULL, sigma2 REAL,
  written_at TEXT NOT NULL, PRIMARY KEY(program, version, day));
CREATE TABLE IF NOT EXISTS mrl_stats(program TEXT NOT NULL, version INTEGER NOT NULL, day TEXT NOT NULL,
  rule_h TEXT NOT NULL, a REAL NOT NULL, g REAL NOT NULL, nb INTEGER NOT NULL, PRIMARY KEY(program, version, day, rule_h));
CREATE TABLE IF NOT EXISTS mrl_walk(program TEXT NOT NULL, version INTEGER NOT NULL, day TEXT NOT NULL,
  position INTEGER NOT NULL, event TEXT NOT NULL, rule_h TEXT NOT NULL, lcb REAL NOT NULL, nb INTEGER NOT NULL,
  qualified INTEGER NOT NULL, PRIMARY KEY(program, version, day, position));
"""
#: Every mrl_* table (league/events/births.py `FACTS_DENY` refuses each; the report reads none but `mrl_decisions`'
#: counts).
TABLES = frozenset({"mrl_decisions", "mrl_pool", "mrl_state", "mrl_stats", "mrl_walk"})

# ---------------------------------------------------------------------------------------------- the vocabulary
GROUPS_O1: dict[str, tuple[str, ...]] = {
    "FAM": ("news-on", "news-day", "8k", "ern", "ins", "price"),
    "SCORE": ("s>=1", "s>=2", "s=3", "s<=-1", "smiss"),
    "GUIDE": ("raised", "lowered"),
    "SRC": ("bz", "other"),
    "HOUR": ("h16-20", "h20-04", "h04-08", "h08-0930", "h0930-12", "h12-16"),
    "COV": ("c0", "c1-3", "c4+"),
    "LIQ": ("adv<10M", "adv10-100M", "adv>=100M"),
    "PX": ("px<10", "px10-50", "px>=50"),
    "VOL": ("sd<2%", "sd2-4%", "sd>=4%"),
    "R5": ("r5<=-5%", "r5mid", "r5>=+5%"),
    "R20": ("r20<=-10%", "r20mid", "r20>=+10%"),
}
GROUPS_ON: dict[str, tuple[str, ...]] = dict(GROUPS_O1, REACT=("re<=0.96", "remid", "re>=1.04"),
                                             GAP=("gap<=0.98", "gapmid", "gap>=1.02"))
GROUPS = {"o1": GROUPS_O1, "on": GROUPS_ON}


def group_of(groups: Mapping[str, Sequence[str]]) -> dict[str, str]:
    return {f: g for g, fs in groups.items() for f in fs}


def grid_rules(groups: Mapping[str, Sequence[str]]) -> list[str]:
    """Every single feature and every pair of features of DIFFERENT groups, as ids 'g:<f>' and 'g:<f1>&<f2>' (the two
    names in Python string order). O1: 39 features, 720 sub-rules; ON: 45 and 969."""
    gof = group_of(groups)
    feats = sorted(gof)
    out = [f"g:{f}" for f in feats]
    for i, a in enumerate(feats):
        for b in feats[i + 1:]:
            if gof[a] != gof[b]:
                out.append(f"g:{a}&{b}")
    return out


def _bin3(x: float | None, lo: float, hi: float, names: Sequence[str]) -> str | None:
    if x is None or not math.isfinite(x):
        return None
    return names[0] if x <= lo else (names[2] if x >= hi else names[1])


def et_hour_bin(hour: int, minute: int) -> str:
    hm = hour * 60 + minute
    if 16 * 60 <= hm < 20 * 60:
        return "h16-20"
    if hm >= 20 * 60 or hm < 4 * 60:
        return "h20-04"
    if hm < 8 * 60:
        return "h04-08"
    if hm < 9 * 60 + 30:
        return "h08-0930"
    if hm < 12 * 60:
        return "h0930-12"
    return "h12-16"


def features(m: Mapping[str, Any], auction: str) -> frozenset[str]:
    """The binary features of a member from its stored-before-tau inputs (meta_spec.py `features`, word for word): fam,
    score (an `ok` verdict answered before tau, else None), guidance, source (news), knowable hour (ET, (h, m)), cov72,
    adv20, prev_close, closes20 (oldest first), and for ON react and gap. A missing input switches its group off,
    except SCORE, whose 'smiss' says no score."""
    f: set[str] = set()
    fam = m.get("fam")
    if fam in GROUPS_O1["FAM"]:
        f.add(fam)
    s = m.get("score")
    if s is None:
        f.add("smiss")
    else:
        s = int(s)
        if s >= 1:
            f.add("s>=1")
        if s >= 2:
            f.add("s>=2")
        if s == 3:
            f.add("s=3")
        if s <= -1:
            f.add("s<=-1")
    g = m.get("guidance")
    if g in ("raised", "lowered"):
        f.add(g)
    if fam in ("news-on", "news-day"):
        src = str(m.get("source") or "").strip().lower()
        if src:
            f.add("bz" if src == "benzinga" else "other")
    hm = m.get("hour_et")
    if hm is not None:
        f.add(et_hour_bin(int(hm[0]), int(hm[1])))
    cov = m.get("cov72")
    if cov is not None:
        f.add("c0" if cov == 0 else ("c1-3" if cov <= 3 else "c4+"))
    adv = m.get("adv20")
    if adv is not None:
        f.add("adv<10M" if adv < 10e6 else ("adv10-100M" if adv < 100e6 else "adv>=100M"))
    px = m.get("prev_close")
    if px is not None:
        f.add("px<10" if px < 10 else ("px10-50" if px < 50 else "px>=50"))
    cl = m.get("closes20")
    if cl and len(cl) == 20 and all(c and c > 0 for c in cl):
        lr = [math.log(cl[i + 1] / cl[i]) for i in range(19)]
        mu = sum(lr) / 19
        sd = math.sqrt(sum((x - mu) ** 2 for x in lr) / 18)
        f.add("sd<2%" if sd < 0.02 else ("sd2-4%" if sd < 0.04 else "sd>=4%"))
        f.add(_bin3(cl[-1] / cl[-6] - 1.0, -0.05, 0.05, GROUPS_O1["R5"]))
        f.add(_bin3(cl[-1] / cl[0] - 1.0, -0.10, 0.10, GROUPS_O1["R20"]))
    if auction == "on":
        if m.get("react") is not None:
            f.add(_bin3(m["react"], 0.96, 1.04, GROUPS_ON["REACT"]))
        if m.get("gap") is not None:
            f.add(_bin3(m["gap"], 0.98, 1.02, GROUPS_ON["GAP"]))
    return frozenset(x for x in f if x)


def rules_of(feats: Iterable[str], tags: Iterable[str], gof: Mapping[str, str], xrules: Iterable[str] = (),
             family: set[str] | None = None) -> set[str]:
    """The sub-rules a member satisfies: its singles, its cross-group pairs, `p:<program>:<version>` for every source
    holding an intent on it (its tags) and `x:<record>` for every PX record selecting it; within `family` when given
    (the cap)."""
    fs = sorted(feats)
    out = {f"g:{a}" for a in fs}
    for i, a in enumerate(fs):
        for b in fs[i + 1:]:
            if gof.get(a) != gof.get(b):
                out.add(f"g:{a}&{b}")
    out.update(f"p:{t}" for t in tags)
    out.update(f"x:{r}" for r in xrules)
    return out if family is None else out & family


# ---------------------------------------------------------------------------------------------- the state
def session_stats(members: Sequence[Mapping[str, Any]]) -> tuple[dict[str, tuple[int, float]], int, float, float]:
    """One ENTERED session: members with keys rules (set), a and tradable. ({rule: (n, sum a)}, n_pool, P_s, the
    session's winsorised within variance)."""
    rows = [m for m in members if m.get("tradable")]
    n = len(rows)
    if n == 0:
        return {}, 0, 0.0, 0.0
    Pm = math.fsum(m["a"] for m in rows) / n
    var = math.fsum(min(max(m["a"] - Pm, -WINSOR), WINSOR) ** 2 for m in rows) / max(n - 1, 1)
    acc: dict[str, list] = {}
    for m in rows:
        for j in m["rules"]:
            c = acc.setdefault(j, [0, 0.0])
            c[0] += 1
            c[1] += m["a"]
    return {j: (c[0], c[1]) for j, c in acc.items()}, n, Pm, var


def state(sessions: Sequence[tuple[dict[str, tuple[int, float]], int, float, float]]) -> dict[str, tuple[float, float, int]]:
    """{rule: (A, G, NB)} over the ENTERED sessions in session order (the last is the newest, weight 1)."""
    var = [v for (_, n, _, v) in sessions if n > 0]
    s2 = max(VAR_FLOOR, (math.fsum(var) / len(var)) if var else VAR_FLOOR)
    N = len(sessions)
    out: dict[str, list] = {}
    for i, (stats, n, Pm, _) in enumerate(sessions):
        if n == 0:
            continue
        w = 2.0 ** (-(N - 1 - i) / H)
        for j, (nj, sj) in stats.items():
            rel = sj / nj - Pm
            Vj = SF ** 2 + s2 / nj
            c = out.setdefault(j, [0.0, 0.0, 0])
            c[0] += w / Vj
            c[1] += w * rel / Vj
            c[2] += 1
    return {j: (c[0], c[1], c[2]) for j, c in out.items()}


def sigma2_of(sessions: Sequence[tuple[Any, int, float, float]]) -> float:
    var = [v for (_, n, _, v) in sessions if n > 0]
    return max(VAR_FLOOR, (math.fsum(var) / len(var)) if var else VAR_FLOOR)


def posterior(A: float, G: float) -> tuple[float, float, float]:
    prec = A + TAU ** -2
    mean = G / prec
    sd = prec ** -0.5
    return mean, sd, mean - Z * sd


def walk(members: Sequence[Mapping[str, Any]], st: Mapping[str, tuple[float, float, int]], cbar: float, *,
         session_index: int) -> list[tuple[str, str, float]]:
    """THE PICKS of one decision: [(event, rule, lcb)] in rank order (meta_spec.py `walk`). session_index: the entered
    sessions of the state (section 7.5, WARM)."""
    if session_index <= WARM:
        return []
    awake: dict[str, set] = {}
    for m in members:
        if not m.get("eligible"):
            continue
        for j in m["rules"]:
            awake.setdefault(j, set()).add(m["event"])
    qual = []
    for j in awake:
        A, G, NB = st.get(j, (0.0, 0.0, 0))
        if NB < MINB:
            continue
        mean, sd, lcb = posterior(A, G)
        if -cbar + lcb > HURDLE:
            qual.append((-lcb, -NB, j, lcb))
    qual.sort()
    order = sorted((m for m in members if m.get("eligible")), key=lambda m: (-float(m.get("adv20") or 0.0), m["event"]))
    taken: set[str] = set()
    ciks: set[str] = set()
    out = []
    for _, _, j, lcb in qual:
        for m in order:
            if len(out) >= K:
                return out
            if m["event"] in taken or m["cik"] in ciks or j not in m["rules"]:
                continue
            taken.add(m["event"])
            ciks.add(m["cik"])
            out.append((m["event"], j, lcb))
    return out


def qualified(members: Sequence[Mapping[str, Any]], st: Mapping[str, tuple[float, float, int]], cbar: float) -> int:
    """How many awake sub-rules qualified (the walk's count, `mrl_walk` only)."""
    awake = {j for m in members if m.get("eligible") for j in m["rules"]}
    n = 0
    for j in awake:
        A, G, NB = st.get(j, (0.0, 0.0, 0))
        if NB >= MINB and -cbar + posterior(A, G)[2] > HURDLE:
            n += 1
    return n


def cbar_of(members: Sequence[Mapping[str, Any]]) -> float:
    """The pool's mean replay round-trip cost of its eligible members (fractions)."""
    xs = [float(m["cost_rt"]) for m in members if m.get("eligible") and m.get("cost_rt") is not None]
    return math.fsum(xs) / len(xs) if xs else 0.0


def rule_hash(rule: str) -> str:
    """F8: a sub-rule's id as the mrl_* tables keep it: sha256("EVL8-MRL|" + id), 16 hex digits."""
    return hashlib.sha256(f"EVL8-MRL|{rule}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------------------------- the store
def ensure(store: Any) -> None:
    """The mrl_* tables in the lane's events.sqlite (additive, idempotent)."""
    store.db.executescript(SCHEMA)


def has_tables(db: Any) -> bool:
    try:
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mrl_decisions'").fetchone() is not None
    except sqlite3.Error:
        return False


def sources(auction: str, at: dt.datetime) -> list[P.Program]:
    """SOURCES(X) at a decision (section 7.2): every program version registered before `at`, other than EVL-META-* (and
    the placebos and POOL records, which are no rows), with hold 1 and X's entry and exit auctions (O1: D's open to D's
    close; ON: D's close to the next open), in programs.py's order."""
    out = []
    for p in P.PROGRAMS:
        if P.is_meta8(p) or p.hold != 1:
            continue
        if auction == "o1" and not (p.entry_at == "open" and p.exit_at == "close"):
            continue
        if auction == "on" and not (p.entry_at == "close" and p.exit_at == "open"):
            continue
        try:
            if p.registered_at >= at:
                continue
        except (RuntimeError, ValueError):
            continue
        out.append(p)
    return out


def first_decision(store: Any, day: dt.date, auction: str) -> dict[str, Any] | None:
    """THE LANE'S FIRST FINISHED DECISION of (D, X) (section 7.2): the earliest receipt `decide-open:<D>` (X = O1) or
    `decide-close:<D>` (X = ON) finished with status `ok` or `pending` (league/events/book.py `decided`'s reading); None
    while there is none."""
    job = f"decide-{'open' if auction == 'o1' else 'close'}:{day.isoformat()}"
    row = store.db.execute("SELECT * FROM receipts WHERE job=? AND finished_at IS NOT NULL AND status IN ('ok', 'pending') "
                           "ORDER BY id LIMIT 1", (job,)).fetchone()
    return None if row is None else dict(row)


def entry_at(session: C.Session, auction: str) -> dt.datetime:
    """The meta-learner's ENTRY AUCTION of D: 09:30 ET of D (EVL-META-O1), D's close (EVL-META-ON)."""
    return session.open_at if auction == "o1" else session.close_at


def _bar_end(row: Mapping[str, Any], session: C.Session) -> dt.datetime | None:
    """The end of a lane mark's bar: its stored bar start `t` + 1 minute, else the label's own minute (the 09:30 bar's,
    the T29 bar's)."""
    try:
        if row.get("t"):
            return S.parse_iso(str(row["t"])) + dt.timedelta(minutes=1)
    except (TypeError, ValueError):
        return None
    label = str(row.get("label"))
    if label == "0930":
        return session.open_at + dt.timedelta(minutes=1)
    if label == "1530":
        return session.close_at - P.T29_BEFORE_CLOSE + dt.timedelta(minutes=1)
    return None


class AsOf:
    """THE LANE'S STORE AS A META DECISION OF (D, X) READS IT (section 7.2), whenever it runs: a READ-ONLY connection of
    its own (league/events/book.py `Lane`: `mode=ro`, the book's cache and the documents) on which
    - `marks` is THE MARKS of the decision and nothing else (a TEMP table that shadows the lane's for this connection
      only): D's `1530` and `0930` marks whose bar ends before tau and that were stored (`fetched_at`) at or before the
      finish of the lane's first finished decision of (D, X); every other mark is missing (a REACT row or
      EVL-NEWS-NIGHT2-ON's gap with none takes no pick, as the book's readers say);
    - `eligible_by` is ELIGIBLE TO PICK's cut-off (book.py `universe_rows`, PREREG-EVL-7's E5 reading): the lane's live
      results decided at or before that finish and never later than the meta-learner's entry auction of D.
    Its inputs are stored times alone, so the live decision and every catch-up read the same rows."""

    def __init__(self, store: Any, session: C.Session, auction: str, tau_: dt.datetime, finish: dt.datetime):
        from . import book as EB

        self._lane = EB.Lane(Path(store.root) / S.DB_NAME)
        self.db = self._lane.db
        self.root = self._lane.root
        self.path = self._lane.path
        self.cache: dict[str, Any] = {}
        self.finish = finish
        self.eligible_by = min(finish, entry_at(session, auction))
        self.db.execute("CREATE TEMP TABLE marks AS SELECT * FROM main.marks WHERE 0")
        keep = []
        for r in self.db.execute("SELECT * FROM main.marks WHERE day=? AND label IN ('1530', '0930')",
                                 (session.day.isoformat(),)).fetchall():
            row = dict(r)
            end = _bar_end(row, session)
            try:
                fetched = S.parse_iso(str(row["fetched_at"]))
            except (TypeError, ValueError):
                continue
            if end is not None and end < tau_ and fetched <= finish:
                keep.append(row)
        if keep:
            cols = list(keep[0])
            self.db.executemany(f"INSERT INTO temp.marks({', '.join(cols)}) VALUES({', '.join('?' for _ in cols)})",
                                [tuple(r[c] for c in cols) for r in keep])

    def meta(self, key: str) -> str | None:
        return self._lane.meta(key)

    def get_document(self, digest: str) -> bytes:
        return self._lane.get_document(digest)

    def close(self) -> None:
        self._lane.close()

    def mark(self, symbol: str, label: str) -> float | None:
        row = self.db.execute("SELECT px FROM marks WHERE symbol=? AND label=?", (str(symbol).upper(), label)).fetchone()
        return None if row is None or row[0] is None or not float(row[0]) > 0 else float(row[0])


def _readers(view: AsOf, day: dt.date) -> tuple[Callable[..., float | None], Callable[..., float | None]]:
    """The book's REACT reaction and EVL-NEWS-NIGHT2-ON gap over THE MARKS only (league/events/book.py
    `reaction_reader`, `gap_reader` with no read of their own: a name with no such mark has no price)."""
    from . import book as EB

    return (EB.reaction_reader(view, day, daily=lambda symbol, d: None, minutes=lambda symbol, session: None),
            EB.gap_reader(view, day, opens=lambda symbol, session: None))


def _is_learner(prog: Any) -> bool:
    test = getattr(P, "is_learner", None)
    return bool(test is not None and test(prog))


def source_picks(store: Any, view: AsOf | None, px_db: Any, session: C.Session, auction: str, t: dt.datetime,
                 first: Mapping[str, Any] | None, srcs: Sequence[P.Program]) -> dict[tuple[str, int], list[dict[str, Any]]]:
    """EACH SOURCE'S PICKS of (D, X) BY THE MEMBERS RULE (section 7.2), fixed by stored times alone: {(id, version):
    [{event, cik, symbol, knowable_at}]}.
    - THIS FILE'S PX SEATS AND CONTROLS: the names THE LIVE PX RUN OF (D, X) selected (league/events/px.py
      `live_selections`: its K 40 and its 200 as that run wrote them, never the hourly re-decision's); none with no
      live PX run.
    - A PREREG-EVL-7 LEARNER: its intents of (D, X) its live decision wrote (league/events/learner.py `live_picks`,
      where the tree has it).
    - EVERY OTHER SOURCE, only when the lane's first finished decision of (D, X) NAMES it (league/events/screen.py
      `names`: a part that failed or ran past its bound gives none): its REAL-MONEY READING of D at tau,
      league/events/book.py `picks(view, s, D, decided_at=tau)` over ELIGIBLE TO PICK's rows with the REACT reaction
      and the gap read from THE MARKS (`AsOf`); a source the book reads no rows for gives none.
    Never an hourly re-decision's intents, a by-itself later decision's or a `decide-px` catch-up's."""
    from . import book as EB
    from . import px as PXL
    from . import screen as SN

    out: dict[tuple[str, int], list[dict[str, Any]]] = {}
    day = session.day
    chosen = PXL.live_selections(px_db, day, auction) if px_db is not None else {}
    known = PXL.knowable(session, auction)
    reaction = gap = None
    if view is not None and auction == "on":
        reaction, gap = _readers(view, day)
    for s in srcs:
        key = (s.id, s.version)
        if P.is_px8(s):
            out[key] = [{"event": str(r["event"]), "cik": str(r["cik"]), "symbol": str(r["symbol"]).upper(),
                         "knowable_at": known} for r in chosen.get(s.id, [])]
            continue
        if _is_learner(s):
            try:
                from . import learner as LR     # (PREREG-EVL-7, where the tree carries it)

                rows = LR.live_picks(store, s, day) or []
            except (ImportError, AttributeError, sqlite3.Error, LookupError, ValueError, TypeError):
                rows = []
            got = []
            for r in rows:
                try:
                    at = S.parse_iso(str(r["knowable_at"])) if r.get("knowable_at") else None
                except (TypeError, ValueError):
                    at = None
                got.append({"event": str(r["event"]), "cik": str(r["cik"]), "symbol": str(r["symbol"]).upper(),
                            "knowable_at": at})
            out[key] = got
            continue
        if view is None or first is None or not SN.names(first.get("summary"), SN.program_key(s.id, s.version)):
            continue
        try:
            picks = EB.picks(view, s, day, decided_at=t, reaction=reaction, gap=gap)
        except (LookupError, sqlite3.Error, ValueError, KeyError, TypeError, RuntimeError):
            continue
        out[key] = [{"event": str(c.event), "cik": str(c.cik), "symbol": str(c.symbol).upper(),
                     "knowable_at": S.parse_iso(str(c.knowable_at)) if c.knowable_at else None} for c in picks]
    return out


def members(picks: Mapping[tuple[str, int], Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """MEMBERS of D (section 7.2): one per issuer with a pick read by the members rule (`source_picks`); its EVENT the
    earliest-knowable such pick's event (ties: the lowest id), its TAGS the sources giving one ("<id>:<version>", in
    programs.py's order, then ascending version); `only_px` when every tag is a PX row."""
    order = {(p.id, p.version): i for i, p in enumerate(P.PROGRAMS)}
    far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    by: dict[str, list[tuple[dt.datetime, str, str, tuple[str, int]]]] = {}
    for key, rows in picks.items():
        for r in rows:
            if not r.get("cik"):
                continue
            by.setdefault(str(r["cik"]), []).append((r.get("knowable_at") or far, str(r["event"]), str(r["symbol"]), key))
    out = []
    for cik, rs in sorted(by.items()):
        rs.sort(key=lambda x: (x[0], x[1]))
        first = rs[0]
        tags = sorted({k for *_, k in rs}, key=lambda k: (order.get(k, 10 ** 6), k[1], k[0]))
        out.append({"cik": cik, "event": first[1], "symbol": first[2].upper(),
                    "knowable_at": None if first[0] == far else first[0],
                    "tags": [f"{p}:{v}" for p, v in tags], "only_px": all(P.is_px8(k[0]) for k in tags)})
    return out


def event_knowable(store: Any, event: str) -> dt.datetime | None:
    """A source event's knowable time (`8k:`/`f4:` a filing's, `news:` an article's, `px:` part A's)."""
    kind, _, ident = str(event).partition(":")
    try:
        if kind in ("8k", "f4"):
            row = store.db.execute("SELECT knowable_at FROM filings WHERE accession=?", (ident,)).fetchone()
        elif kind == "news":
            row = store.db.execute("SELECT knowable_at FROM news WHERE id=?", (ident,)).fetchone()
        elif kind == "px":
            from . import px as PXL
            return PXL.event_knowable(store, event)
        else:
            return None
        return None if row is None or row[0] is None else S.parse_iso(str(row[0]))
    except (sqlite3.Error, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------- a member's inputs
def _closes20(store: Any, px_db: Any, symbol: str, day: dt.date) -> list[float] | None:
    """The 20 raw closes of the sessions before D (the lane's `bars`, else px.sqlite's `px_bars`), READ AS STORED
    WHATEVER THEIR WRITE TIME (PREREG-EVL-7 section 1.1's reading), oldest first; None unless all 20 are there."""
    prior = C.previous(store, day, CLOSES)
    if len(prior) < CLOSES:
        return None
    out = []
    for s in prior:
        row = store.db.execute("SELECT c FROM bars WHERE symbol=? AND day=? AND adj='raw'",
                               (symbol, s.day.isoformat())).fetchone()
        c = None if row is None else row[0]
        if c is None and px_db is not None:
            got = px_db.execute("SELECT c FROM px_bars WHERE symbol=? AND day=? AND adj='raw'",
                                (symbol, s.day.isoformat())).fetchone()
            c = None if got is None else got[0]
        if c is None or not float(c) > 0:
            return None
        out.append(float(c))
    return out


def inputs(store: Any, view: AsOf | None, px_marks: Mapping[str, Mapping[str, Any]], px_db: Any, m: Mapping[str, Any],
           day: dt.date, auction: str, t: dt.datetime, uni: Mapping[str, Any] | None) -> dict[str, Any]:
    """A member's feature inputs (section 7.3), every one from rows stored before tau, and for ON the marks from THE
    MARKS (section 7.2): REACT D's lane `1530` mark (`AsOf`), else the live PX run's `px1530` (`px_marks`); GAP D's
    `0930` mark; a mark missing there switches its group off."""
    session = C.session(store, day)
    event = str(m["event"])
    kind, _, ident = event.partition(":")
    out: dict[str, Any] = {"adv20": None if uni is None else _f(uni.get("adv20")),
                           "prev_close": None if uni is None else _f(uni.get("prev_close"))}
    verdict = None
    if kind == "news":
        row = store.db.execute("SELECT * FROM news WHERE id=?", (ident,)).fetchone()
        at = m.get("knowable_at")
        out["fam"] = "news-on" if at is not None and session is not None and at < session.open_cutoff else "news-day"
        if row is not None:
            out["source"] = row["source"]
        verdict = V.stored(store, event, V.PROMPTS["news"])
    elif kind == "8k":
        row = store.db.execute("SELECT items FROM filings WHERE accession=?", (ident,)).fetchone()
        items = set(json.loads(row["items"] or "[]")) if row is not None else set()
        out["fam"] = "ern" if "2.02" in items else "8k"
        verdict = V.stored(store, event, V.PROMPTS["doc"])
    elif kind == "f4":
        out["fam"] = "ins"
    elif kind == "px":
        out["fam"] = "price"
    if verdict and verdict.get("status") == "ok" and verdict.get("answered_at") and \
            S.parse_iso(str(verdict["answered_at"])) < t:
        out["score"] = verdict.get("score")
        out["guidance"] = verdict.get("guidance")
    at = m.get("knowable_at")
    if at is not None:
        local = at.astimezone(C.NY)
        out["hour_et"] = (local.hour, local.minute)
        sym = str(m["symbol"]).upper()
        n = 0
        for r in store.db.execute("SELECT id, symbols, received_at FROM news WHERE knowable_at>=? AND knowable_at<?",
                                  (S.iso(at - COV_WINDOW), S.iso(at))):
            if f"news:{r['id']}" == event:
                continue
            try:
                syms = json.loads(r["symbols"] or "[]")
            except ValueError:
                continue
            if isinstance(syms, list) and len(syms) == 1 and str(syms[0]).upper() == sym and \
                    S.parse_iso(str(r["received_at"])) < t:
                n += 1
        out["cov72"] = n
    out["closes20"] = _closes20(store, px_db, str(m["symbol"]).upper(), day)
    if auction == "on" and out.get("prev_close"):
        sym = str(m["symbol"]).upper()
        react = view.mark(sym, "1530") if view is not None else None
        if react is None:
            got = px_marks.get(sym)
            react = _f(got.get("px")) if got is not None else None
        gap = view.mark(sym, "0930") if view is not None else None
        out["react"] = None if react is None else react / float(out["prev_close"])
        out["gap"] = None if gap is None else gap / float(out["prev_close"])
    return out



def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _held(store: Any, prog: Any, cik: str, day: dt.date) -> bool:
    return P._held_recently(store, prog, cik, day)


# ---------------------------------------------------------------------------------------------- the outcomes (F9)
def member_outcome(store: Any, cik: str, day: dt.date, auction: str, tags: Sequence[str], before: dt.datetime
                   ) -> dict[str, Any]:
    """A MEMBER'S OUTCOME (F9, section 7.2's one reading): the settled `outcomes` row, under the FIRST of its tags
    (programs.py's order, then ascending version: `tags` is in that order) that holds one, of THAT TAG'S INTENT OF THE
    ISSUER entering at D's X auction with the member's exit auction (each tag prices the same issuer at the same two
    auctions; PREREG-EVL-7 section 1.1's POOL OUTCOME reading), settled before `before`. NO OUTCOME ({status:
    "terminal"}) when its RAW ENTRY PRINT was above 1.25 x the raw SIP close of the session before D (PREREG-EVL-2's
    LIMIT AT ENTRY) or that cannot be read, or not TRADABLE, or when no tag will ever hold one (every tag's intent of the
    issuer skipped, or none); {status: "pending"} while one may still come. Only a TRADABLE outcome is {status:
    "settled", a, tradable}. ONE READING (release 1019n's second judges review), for the POOL (`pool_record`) and the
    state (section 7.4) alike: a tag AHEAD whose intent of the issuer may still settle (planned or entered, or settled
    only at or after `before`) makes the member PENDING; the next tag's settled outcome is never read in its place,
    since the first tag that holds one may yet be that tag. A tag whose intent ended with none (skipped) is passed."""
    entry, exit_ = ("open", "close") if auction == "o1" else ("close", "open")
    for tag in tags:
        pid, _, ver = tag.rpartition(":")
        intent = store.db.execute("SELECT * FROM intents WHERE program=? AND version=? AND cik=? AND entry_day=? AND "
                                  "entry_at=? AND exit_at=? ORDER BY (status LIKE 'skipped%'), event LIMIT 1",
                                  (pid, int(ver), str(cik), day.isoformat(), entry, exit_)).fetchone()
        if intent is None or str(intent["status"]).startswith("skipped"):
            continue
        row = store.db.execute("SELECT * FROM outcomes WHERE program=? AND version=? AND event=? AND status='settled'",
                               (pid, int(ver), str(intent["event"]))).fetchone()
        if row is None or S.parse_iso(str(row["settled_at"])) >= before:
            if str(intent["status"]) in ("planned", "entered") or row is not None:
                return {"status": "pending", "program": pid, "version": int(ver)}
            continue
        if not _within_limit(store, dict(intent), dict(row)):
            return {"status": "terminal", "why": "limit at entry"}
        if not row["tradable"]:
            return {"status": "terminal", "why": "not tradable"}
        return {"status": "settled", "a": float(row["a"]), "r": None if row["r"] is None else float(row["r"]),
                "tradable": True, "program": pid, "version": int(ver), "event": str(intent["event"]),
                "exit_day": None if intent["exit_day"] is None else str(intent["exit_day"])}
    return {"status": "terminal", "why": "no outcome"}


def _within_limit(store: Any, intent: Mapping[str, Any], outcome: Mapping[str, Any]) -> bool:
    """PREREG-EVL-2's LIMIT AT ENTRY for every member (F9): the raw entry print at most 1.25 x the raw SIP close of the
    session before D; False when either cannot be read (the reading that trades less). The print and the close are where
    the member's own settlement read them (league/events/score.py): a lane event's in the lane's `marks` and `universe`
    (else the adjusted entry price over the lane's adjusted-to-raw ratio of the day); A PX EVENT'S (`px:...`) IN
    px.sqlite's `px_marks` and `px_universe` (section 4.4: a PX event is settled on px.sqlite alone; else the adjusted
    entry over px_bars' ratio), never the lane's."""
    from . import score as SC

    symbol, day = str(intent["symbol"]).upper(), str(intent["entry_day"])
    label = "open" if intent["entry_at"] == "open" else "close"
    entry = _f(outcome.get("entry_px"))
    px_event = SC.px_event(intent)
    raw = prev = None
    if not px_event:
        row = store.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label=? AND px IS NOT NULL",
                               (symbol, day, label)).fetchone()
        raw = None if row is None else _f(row[0])
        if raw is None:
            ratio = SC._ratio(store, symbol, dt.date.fromisoformat(day))
            raw = None if entry is None or not ratio else entry / ratio
        u = store.db.execute("SELECT prev_close FROM universe WHERE day=? AND symbol=?", (day, symbol)).fetchone()
        prev = None if u is None else _f(u[0])
    from . import px as PXL

    db = PXL.read_only(Path(store.root)) if hasattr(store, "root") else None
    if db is not None:
        try:
            if px_event:
                row = db.execute("SELECT px FROM px_marks WHERE symbol=? AND day=? AND label=? AND px IS NOT NULL",
                                 (symbol, day, label)).fetchone()
                raw = None if row is None else _f(row[0])
                if raw is None and entry is not None:
                    bars = {str(r["adj"]): _f(r["c"]) for r in db.execute(
                        "SELECT adj, c FROM px_bars WHERE symbol=? AND day=?", (symbol, day))}
                    rc, ac = bars.get("raw"), bars.get("all")
                    raw = entry / (ac / rc) if rc and ac else entry
            if prev is None:
                got = db.execute("SELECT prev_close FROM px_universe WHERE day=? AND symbol=? AND rule='live'",
                                 (day, symbol)).fetchone()
                prev = None if got is None else _f(got[0])
        except sqlite3.Error:
            return False
        finally:
            db.close()
    return raw is not None and prev is not None and raw <= LIMIT_MULTIPLE * prev


# ---------------------------------------------------------------------------------------------- the family
def family(auction: str, at: dt.datetime) -> tuple[list[str], set[str]]:
    """THE FAMILY of a decision (section 7.3): the grid (720 / 969), the program experts of its sources in their
    registration order, the PX record experts of its window (`x:<record>`, part A's O1 or ON records; C1 never) and
    no ledger expert (harness H6 has not shipped); never above FAMILY_CAP (at the cap a new program expert joins only in
    place of the newest ledger expert: with none to drop it never joins). (the ordered list, the set)"""
    from . import px as PXL

    rules = grid_rules(GROUPS[auction])
    try:
        recs = [f"x:{r['id']}" for r in PXL.records("O1" if auction == "o1" else "ON")]
    except (OSError, ValueError):
        recs = []
    progs = sorted(sources(auction, at), key=lambda p: (p.registered_at, P.PROGRAMS.index(p) if p in P.PROGRAMS else 0))
    out = rules + recs
    for p in progs:
        if len(out) >= FAMILY_CAP:
            break
        out.append(f"p:{p.id}:{p.version}")
    return out, set(out)


# ---------------------------------------------------------------------------------------------- the times
def tau(session: C.Session, auction: str) -> dt.datetime:
    return session.open_decide if auction == "o1" else session.close_decide


def sigma_time(session: C.Session, auction: str) -> dt.datetime:
    """Section 7.4's STATE TIME: 09:00:00 ET of D (EVL-META-O1), the close - 30 minutes (EVL-META-ON)."""
    return session.at(SIGMA_OPEN) if auction == "o1" else session.close_at - SIGMA_CLOSE_BEFORE


def auction_of(prog: Any) -> str:
    return "o1" if getattr(prog, "entry_at", "") == "open" else "on"


def learner(auction: str) -> P.Program8 | None:
    pid = PROGRAM_OF[auction]
    return next((p for p in P.rows_8() if p.id == pid), None)


# ---------------------------------------------------------------------------------------------- the state as of sigma
class Yielded(Exception):
    """A state computation that stopped before its next step because another lane task fell due (section 4.6: the
    pre-pass YIELDS, writing nothing until it is whole); the next turn computes it again from the same stored rows."""


def state_sessions(store: Any, prog: Any, day: dt.date, sig: dt.datetime, fam: set[str], gof: Mapping[str, str],
                   late: Callable[[], bool] | None = None) -> tuple[list[tuple[Any, int, float, float]], int, int]:
    """THE STATE'S SESSIONS (section 7.4) of a decision of D at state time `sig`: every entry session from STATE_FROM
    before D with members written (`mrl_pool`), in session order, that has ENTERED by `sig` (every member settled or
    terminal by `sig`, or IMPUTE_AFTER sessions closed after its scheduled exit, a member still unsettled then at
    IMPUTE_A), each as `session_stats`. (sessions, entered, imputed)"""
    days = [str(r[0]) for r in store.db.execute(
        "SELECT DISTINCT day FROM mrl_pool WHERE program=? AND version=? AND day>=? AND day<? ORDER BY day",
        (prog.id, prog.version, STATE_FROM.isoformat(), day.isoformat()))]
    out = []
    imputed = 0
    closed = [s.day for s in C.sessions(store, STATE_FROM, day) if s.close_at <= sig]
    for d in days:
        if late is not None and late():
            raise Yielded(f"the state of {day.isoformat()} yields before session {d}")
        sday = dt.date.fromisoformat(d)
        exit_s = sday if prog.entry_at == "open" else (C.nth(store, sday, 2).day if C.nth(store, sday, 2) else None)
        rows = [dict(r) for r in store.db.execute("SELECT * FROM mrl_pool WHERE program=? AND version=? AND day=? ORDER BY "
                                                  "cik", (prog.id, prog.version, d))]
        mem = []
        waiting = []
        for r in rows:
            got = member_outcome(store, str(r["cik"]), sday, auction_of(prog), json.loads(r["tags"]), sig)
            rules = rules_of(json.loads(r["features"]), json.loads(r["tags"]), gof, json.loads(r["xrules"]), fam)
            if got["status"] == "settled":
                mem.append({"rules": rules, "a": got["a"], "tradable": True})
            elif got["status"] == "pending":
                waiting.append(rules)
        if waiting:
            after = sum(1 for x in closed if exit_s is not None and x > exit_s)
            if after < IMPUTE_AFTER:
                continue
            imputed += len(waiting)
            mem += [{"rules": rules, "a": IMPUTE_A, "tradable": True} for rules in waiting]
        out.append(session_stats(mem))
    return out, len(out), imputed


def compute_state(store: Any, prog: Any, day: dt.date, sig: dt.datetime, late: Callable[[], bool] | None = None
                  ) -> dict[str, Any]:
    """The state as of `sig` (section 7.4): {stats: {rule: (A, G, NB)}, entered, imputed, sigma2}. `late`: a yield
    before each session's step (`Yielded`)."""
    auction = auction_of(prog)
    fam_list, fam = family(auction, sig)
    gof = group_of(GROUPS[auction])
    sessions, entered, imputed = state_sessions(store, prog, day, sig, fam, gof, late)
    return {"stats": state(sessions), "entered": entered, "imputed": imputed, "sigma2": sigma2_of(sessions)}


def stored_state(store: Any, prog: Any, day: dt.date, sig: dt.datetime) -> dict[str, Any] | None:
    """The pre-pass's stored state of (D, prog) at `sig` (`mrl_state` / `mrl_stats`), rules by their hash; None when
    none is stored."""
    row = store.db.execute("SELECT * FROM mrl_state WHERE program=? AND version=? AND day=? AND sigma=?",
                           (prog.id, prog.version, day.isoformat(), S.iso(sig))).fetchone()
    if row is None:
        return None
    stats = {str(r["rule_h"]): (float(r["a"]), float(r["g"]), int(r["nb"])) for r in store.db.execute(
        "SELECT * FROM mrl_stats WHERE program=? AND version=? AND day=?", (prog.id, prog.version, day.isoformat()))}
    return {"hashed": stats, "entered": int(row["entered"]), "imputed": int(row["imputed"]), "sigma2": row["sigma2"]}


def write_state(store: Any, prog: Any, day: dt.date, sig: dt.datetime, got: Mapping[str, Any], *, run: str,
                now: dt.datetime) -> bool:
    """The state of (D, prog) at `sig`, WRITE-ONCE (`mrl_state`, `mrl_stats` by rule hash), with the run's id."""
    with store.tx() as db:
        cur = db.execute("INSERT OR IGNORE INTO mrl_state(program, version, day, sigma, run, entered, imputed, sigma2, "
                         "written_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (prog.id, prog.version, day.isoformat(), S.iso(sig), run, int(got["entered"]),
                          int(got["imputed"]), got.get("sigma2"), S.iso(now)))
        if cur.rowcount != 1:
            return False
        for j, (A, G, NB) in got["stats"].items():
            db.execute("INSERT OR IGNORE INTO mrl_stats(program, version, day, rule_h, a, g, nb) VALUES(?, ?, ?, ?, ?, ?, ?)",
                       (prog.id, prog.version, day.isoformat(), rule_hash(j), float(A), float(G), int(NB)))
    return True


def prepass(store: Any, day: dt.date, auction: str, *, now: dt.datetime, run: str,
            late: Callable[[], bool] | None = None) -> dict[str, Any]:
    """THE STATE PRE-PASS (`prepass-meta:<open|close>:<D>`, section 4.6): the meta-learner's state as of its state time,
    computed at or after it and stored once, WHOLE (it yields before each step when `late` says another task is due:
    `Yielded`, nothing written). Counts only."""
    prog = learner(auction)
    if prog is None:
        return {"skipped": "PREREG-EVL-8 is not pinned"}
    session = C.session(store, day)
    if session is None:
        return {"skipped": "no session"}
    sig = sigma_time(session, auction)
    if now < sig:
        raise ValueError(f"the state of {day} {auction} is computed at or after its state time {S.iso(sig)}")
    ensure(store)
    got = compute_state(store, prog, day, sig, late)
    wrote = write_state(store, prog, day, sig, got, run=run, now=now)
    return {"day": day.isoformat(), "auction": auction, "entered": got["entered"], "written": wrote}


# ---------------------------------------------------------------------------------------------- the decision
def decided(db: Any, prog: Any, day: dt.date) -> dict[str, Any] | None:
    """The meta-learner's decision of D on record ({kind, status, ...}), None while none."""
    if not has_tables(db):
        return None
    row = db.execute("SELECT * FROM mrl_decisions WHERE program=? AND version=? AND day=?",
                     (getattr(prog, "id", prog), int(getattr(prog, "version", 1)), day.isoformat())).fetchone()
    return None if row is None else dict(row)


def live_allowed(store: Any, session: C.Session, auction: str) -> bool:
    from . import px as PXL

    return PXL.live_allowed(store, session, auction)


def decide(store: S.Store, day: dt.date, auction: str, *, now: Callable[[], dt.datetime], kind: str = "live",
           late: Callable[[], bool] | None = None) -> dict[str, Any]:
    """ONE META DECISION OF (D, X) (section 7.5), by itself, under its own receipt (`JOB_LIVE`, or `JOB_CATCHUP` for a
    catch-up), written once: the members by the cutoff, their features and PX record rules (`mrl_pool`), the state as
    of sigma (the pre-pass's stored state, or the same computed here), the walk (`mrl_walk`), its picks as intents
    (rank_key K + 1 - position, why "mrl"), its decision row (`mrl_decisions`, kind live or catchup, the code's sha).
    A session before REGISTERED_AT_8 builds the state only (members and their outcomes, no pick). A part that does not
    finish (`late`) writes no decision row and is decided later by a catch-up. Counts only in the receipt (F8)."""
    prog = learner(auction)
    if prog is None:
        return {"skipped": "PREREG-EVL-8 is not pinned"}
    session = C.session(store, day)
    if session is None:
        return {"skipped": "no session"}
    ensure(store)
    if decided(store.db, prog, day) is not None:
        return {"skipped": f"{prog.id} {day.isoformat()} is decided already"}
    t = tau(session, auction)
    if kind == "live" and not live_allowed(store, session, auction):
        return {"skipped": "not live: before the release or the registration (a catch-up decides it)"}
    started = now()
    if started < t:
        raise ValueError(f"a meta decision of {day} runs at or after its tau {S.iso(t)}")
    job = f"{JOB_LIVE[auction]}:{day.isoformat()}" if kind == "live" else \
        f"{JOB_CATCHUP}:{'open' if auction == 'o1' else 'close'}:{day.isoformat()}"
    from . import px as PXL

    if kind == "live" and PXL.live_ran(store, job):
        # (section 7.7: a META part that did not finish in its bound is never traded at that auction; it is decided by
        # its catch-up alone, never by a second live run)
        return {"skipped": f"its live run {job} ran already: a catch-up decides it"}
    rid = store.start_receipt(job, now=started)

    out: dict[str, Any] = {"day": day.isoformat(), "auction": auction, "kind": kind, "code_sha": CODE_SHA,
                           "release": PXL.release_id()}
    try:
        got = _decide(store, prog, session, auction, t, started, now=now, kind=kind, late=late, receipt=rid)
    except Exception as exc:  # noqa: BLE001 - its failure is its own: a catch-up decides it later
        store.finish_receipt(rid, "failed", out | {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, now=now())
        return out | {"_status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    out.update(got)
    status = str(out.pop("_status", "ok"))
    store.finish_receipt(rid, status, out, now=now())
    return out | {"_status": status}


def _decide(store: S.Store, prog: Any, session: C.Session, auction: str, t: dt.datetime, started: dt.datetime, *,
            now: Callable[[], dt.datetime], kind: str, late: Callable[[], bool] | None, receipt: int) -> dict[str, Any]:
    from . import book as EB
    from . import px as PXL
    from . import score as SC

    day = session.day
    srcs = sources(auction, t)
    first = first_decision(store, day, auction)
    finish = S.parse_iso(str(first["finished_at"])) if first is not None else None
    root = getattr(store, "root", None)
    px_db = PXL.read_only(Path(root)) if root is not None else None
    view = AsOf(store, session, auction, t, finish) if finish is not None and root is not None else None
    try:
        picked = source_picks(store, view, px_db, session, auction, t, first, srcs)
        mem = members(picked)
        values = PXL.live_features(px_db, day, auction) if px_db is not None else {}
        recs = PXL.records("O1" if auction == "o1" else "ON") if values else []
        chosen = PXL.live_selections(px_db, day, auction) if values else {}
        seats_of = {pid: {str(r["cik"]) for r in rows} for pid, rows in chosen.items()}
        selected = {r["id"]: PXL.select_record(r, values, seat_events=seats_of) for r in recs}
        px_marks = PXL.live_marks(px_db, day) if (px_db is not None and auction == "on") else {}
        uni_all = EB.universe_rows(view, day) if view is not None else {}
        prev = C.previous(store, day, 1)
        equity = SC.equity_on(store, prev[0].day) if prev else None
        reg = prog.registered_at
        fam_list, fam = family(auction, t)
        gof = group_of(GROUPS[auction])
        pool = []
        for m in mem:
            if late is not None and late():
                return {"_status": "cut", "cut": "the part's bound passed"}
            uni = uni_all.get(m["cik"])
            if uni is None and m["only_px"] and px_db is not None:
                got = px_db.execute("SELECT * FROM px_universe WHERE day=? AND cik=? AND rule='live' AND decided_at<?",
                                    (day.isoformat(), m["cik"], S.iso(t))).fetchone()
                uni = None if got is None else dict(got)
            inp = inputs(store, view, px_marks, px_db, m, day, auction, t, uni)
            feats = sorted(features(inp, auction))
            xr = sorted(r for r, sel in selected.items() if m["cik"] in sel)
            known = m.get("knowable_at")
            tradable = bool(uni is not None and equity is not None and uni.get("prev_close") is not None and
                            LIMIT_MULTIPLE * float(uni["prev_close"]) <= TRADABLE_SHARE * float(equity))
            eligible = bool(uni is not None and known is not None and known > reg and tradable and
                            not _held(store, prog, m["cik"], day))
            adv = None if uni is None else _f(uni.get("adv20"))
            cost = None
            if adv is not None:
                cost = (SC.cost_bp(adv, equity, "entry") + SC.cost_bp(adv, equity, "exit")) / 1e4
            pool.append({**m, "features": feats, "xrules": xr, "eligible": eligible, "adv20": adv,
                         "prev_close": None if uni is None else _f(uni.get("prev_close")), "cost_rt": cost,
                         "rules": rules_of(feats, m["tags"], gof, xr, fam)})
    finally:
        if view is not None:
            view.close()
        if px_db is not None:
            px_db.close()
    sig = sigma_time(session, auction)
    have = stored_state(store, prog, day, sig)
    if have is None:        # (no pre-pass state: the same state, from the same stored times, computed and kept here)
        computed = compute_state(store, prog, day, sig)
        write_state(store, prog, day, sig, computed, run=f"{JOB_LIVE[auction] if kind == 'live' else JOB_CATCHUP}#"
                    f"{receipt}", now=now())
        st = computed["stats"]
        entered, imputed = computed["entered"], computed["imputed"]
    else:
        wanted = {j for m in pool for j in m["rules"]}
        st = {j: have["hashed"][h] for j in wanted for h in [rule_hash(j)] if h in have["hashed"]}
        entered, imputed = have["entered"], have["imputed"]
    cbar = cbar_of(pool)
    picks = walk(pool, st, cbar, session_index=entered) if t > prog.registered_at else []
    nq = qualified(pool, st, cbar)
    if late is not None and late():
        return {"_status": "cut", "cut": "the part's bound passed"}
    exit_s = session if prog.entry_at == "open" else C.nth(store, day, 2)
    with store.tx() as db:
        for m in pool:
            db.execute("INSERT OR IGNORE INTO mrl_pool(program, version, day, cik, symbol, event, knowable_at, tags, features, "
                       "xrules, eligible, adv20, prev_close, cost_rt) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (prog.id, prog.version, day.isoformat(), m["cik"], m["symbol"], m["event"],
                        None if m.get("knowable_at") is None else S.iso(m["knowable_at"]), json.dumps(m["tags"]),
                        json.dumps(m["features"]), json.dumps(m["xrules"]), int(m["eligible"]), m["adv20"],
                        m["prev_close"], m["cost_rt"]))
        by_event = {m["event"]: m for m in pool}
        for pos, (event, rule, lcb) in enumerate(picks, 1):
            m = by_event[event]
            A, G, NB = st.get(rule, (0.0, 0.0, 0))
            db.execute("INSERT OR IGNORE INTO mrl_walk(program, version, day, position, event, rule_h, lcb, nb, qualified) "
                       "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)", (prog.id, prog.version, day.isoformat(), pos, event,
                                                             rule_hash(rule), float(lcb), int(NB), int(nq)))
            if exit_s is None:
                continue
            db.execute("INSERT OR IGNORE INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                       "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'shadow', "
                       "'planned', ?)", (prog.id, prog.version, event, m["symbol"], m["cik"], S.iso(t), day.isoformat(),
                                         prog.entry_at, exit_s.day.isoformat(), prog.exit_at, float(K + 1 - pos), WHY))
        db.execute("INSERT OR IGNORE INTO mrl_decisions(program, version, day, kind, receipt, started_at, finished_at, status, "
                   "code_sha, members, eligible, picks) VALUES(?, ?, ?, ?, ?, ?, ?, 'ok', ?, ?, ?, ?)",
                   (prog.id, prog.version, day.isoformat(), kind, receipt, S.iso(started), S.iso(now()), CODE_SHA,
                    len(pool), sum(1 for m in pool if m["eligible"]), len(picks)))
    return {"members": len(pool), "eligible": sum(1 for m in pool if m["eligible"]), "picks": len(picks),
            "imputed": imputed, "status": "decided"}


def live_picks(db: Any, prog: Any, day: dt.date) -> list[dict[str, Any]]:
    """THE REAL-MONEY PICKS OF A META-LEARNER for D (section 7.7): its intents of D when its LIVE decision wrote them
    (`mrl_decisions` kind live, ok), in rank_key order (then adv20 by the book, then event id); none for a catch-up's."""
    got = decided(db, prog, day)
    if got is None or got.get("kind") != "live" or got.get("status") != "ok":
        return []
    return [dict(r) for r in db.execute("SELECT * FROM intents WHERE program=? AND version=? AND entry_day=? AND why=? "
                                        "ORDER BY rank_key DESC, event", (prog.id, prog.version, day.isoformat(), WHY))]


def member_exit(store: Any, day: dt.date, auction: str) -> dt.date:
    """A member's SCHEDULED EXIT SESSION (hold 1, section 7.1): D itself for EVL-META-O1 (D's open to D's close), the
    session after D for EVL-META-ON (D's close to the next open); while the calendar does not hold that session yet,
    the day after D (no later session can be its exit: the reading that waits)."""
    if auction == "o1":
        return day
    nxt = C.nth(store, day, 2)
    return nxt.day if nxt is not None else day + dt.timedelta(days=1)


def pool_record(store: Any, prog: Any, *, before: dt.datetime | None = None
                ) -> tuple[list[dict[str, Any]], list[tuple[dt.date, dt.date]]]:
    """THE POOL RECORD (EVL-META-O1-POOL / -ON-POOL, section 7.1), the meta-learner's control, as THE META SCREEN reads
    it (section 5.2: PREREG-EVL-6 sections 1.2-2 as frozen): (rows, pending). ROWS: each LIVE decision's members
    ELIGIBLE TO PICK with their settled TRADABLE OUTCOMES (F9) as settled rows {entry_day, exit_day, issuer, event, a,
    r, tradable}, `exit_day` the scheduled exit of the tag intent whose outcome it is (else `member_exit`), so a look as
    of the close X covers the members whose scheduled exits are at or before it, as it covers every control's events.
    PENDING: (entry_day, scheduled exit) of every such member whose outcome may still come (`member_outcome`
    "pending"): PREREG-EVL-6 section 2's FINALITY, "every intent of the version and of its control scheduled to exit by
    X has settled", holds a look as of X while one exits by X. A member with NO OUTCOME (its limit at entry, not
    tradable, none ever) is neither."""
    out: list[dict[str, Any]] = []
    pending: list[tuple[dt.date, dt.date]] = []
    now = before or S.utc_now()
    auction = auction_of(prog)
    for d in store.db.execute("SELECT day FROM mrl_decisions WHERE program=? AND version=? AND kind='live' AND status='ok' "
                              "ORDER BY day", (prog.id, prog.version)).fetchall():
        day = dt.date.fromisoformat(str(d[0]))
        scheduled = member_exit(store, day, auction)
        for r in store.db.execute("SELECT * FROM mrl_pool WHERE program=? AND version=? AND day=? AND eligible=1",
                                  (prog.id, prog.version, day.isoformat())).fetchall():
            got = member_outcome(store, str(r["cik"]), day, auction, json.loads(r["tags"]), now)
            if got["status"] == "pending":
                pending.append((day, scheduled))
                continue
            if got["status"] != "settled":
                continue
            exit_day = dt.date.fromisoformat(str(got["exit_day"])[:10]) if got.get("exit_day") else scheduled
            out.append({"entry_day": day, "exit_day": exit_day, "issuer": str(r["cik"]), "event": str(r["event"]),
                        "a": got["a"], "r": got.get("r"), "tradable": True})
    return out, pending


def pool_rows(store: Any, prog: Any, *, before: dt.datetime | None = None) -> list[dict[str, Any]]:
    """THE POOL RECORD's settled rows (`pool_record`'s first part)."""
    return pool_record(store, prog, before=before)[0]


def report_lines(store: Any, day: dt.date) -> dict[str, Any]:
    """THE REPORT'S META BLOCK of D (section 10), COUNTS ONLY: members, members eligible to pick, picks written, imputed
    members, decision status (live, cut, catch-up) and the share of the run's sessions decided live. No LCB, sub-rule,
    hash or figure."""
    if not P.registers_8() or not has_tables(store.db):
        return {}
    out: dict[str, Any] = {}
    reg = P.REGISTERED_AT_8
    for auction, pid in PROGRAM_OF.items():
        row = store.db.execute("SELECT kind, status, members, eligible, picks FROM mrl_decisions WHERE program=? AND "
                               "version=1 AND day=?", (pid, day.isoformat())).fetchone()
        imp = store.db.execute("SELECT imputed FROM mrl_state WHERE program=? AND version=1 AND day=?",
                               (pid, day.isoformat())).fetchone()
        # (the share of the run's sessions decided LIVE, from the first session after REGISTERED_AT_8: a catch-up is
        # never a judged block, so a share q decided by catch-up needs about 1 / (1 - q) times the sessions to a look)
        since = S.parse_iso(str(reg)).astimezone(C.NY).date().isoformat() if reg else day.isoformat()
        kinds = store.db.execute("SELECT SUM(kind='live' AND status='ok') AS live, COUNT(*) AS n FROM mrl_decisions WHERE "
                                 "program=? AND version=1 AND day>=? AND day<=?", (pid, since, day.isoformat())).fetchone()
        n = int(kinds["n"] or 0)
        share = None if n == 0 else round(int(kinds["live"] or 0) / n, 4)
        out[pid] = None if row is None else {"kind": row["kind"], "status": row["status"], "members": row["members"],
                                             "eligible": row["eligible"], "picks": row["picks"],
                                             "imputed": None if imp is None else imp["imputed"], "live_share": share}
    return out


__all__ = ["K", "H", "TAU", "SF", "Z", "HURDLE", "MINB", "WARM", "WINSOR", "VAR_FLOOR", "IMPUTE_AFTER", "IMPUTE_A",
           "ISSUER_GAP", "FAMILY_CAP", "LIMIT_MULTIPLE", "TRADABLE_SHARE", "STATE_FROM", "PROGRAM_OF", "POOL_OF",
           "JOB_LIVE", "JOB_CATCHUP", "JOB_PREPASS", "SIGMA_OPEN", "SIGMA_CLOSE_BEFORE", "PREPASS_BUDGET",
           "META_CLOSE_BOUND", "META_CLOSE_UNTIL", "WHY", "CODE_SHA", "SCHEMA", "TABLES", "Yielded",
           "GROUPS_O1", "GROUPS_ON", "GROUPS", "group_of", "grid_rules", "et_hour_bin", "features", "rules_of",
           "session_stats", "state", "sigma2_of", "posterior", "walk", "qualified", "cbar_of", "rule_hash", "ensure",
           "has_tables", "sources", "first_decision", "entry_at", "AsOf", "source_picks", "members", "event_knowable",
           "inputs", "member_outcome", "member_exit", "family", "tau", "sigma_time", "auction_of", "learner",
           "state_sessions", "compute_state", "stored_state", "write_state", "prepass", "decided", "live_allowed",
           "decide", "live_picks", "pool_record", "pool_rows", "report_lines"]
