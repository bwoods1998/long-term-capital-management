"""PREREG-EVL-8 PART A: THE PX LANE (docs/prereg/PREREG-EVL-8.md once frozen; until then
goal-2026-10-19/evl8/PREREG-EVL-8.md, the final text of the fix round). Standard library only. NOTHING HERE DECIDES,
WRITES OR IS CHARGED while league/events/programs.py `REGISTERED_AT_8` is None (`registers_8`): this file's rows are in
no registry, every entry point returns at once and writes nothing.

THE ROWS (league/events/programs.py `ROWS_8`): three seats (PX-DROP-ON, PX-SURGE-ON: D's closing cross -> D+1's
opening cross; PX-GAP-O1: D's opening cross -> D's closing cross) and two controls (CTRL-PX-ALL-ON, CTRL-PX-ALL-O1:
free records), decided here, never by `programs.select` and never inside the lane's decision runs (league/events/run.py
skips `FAMILIES_8`). The 528 records of the pinned grid (`px_grid8.json`, canonical sha256 `GRID_SHA256`, read only
through `grid()`, which refuses any other bytes), the bar-basis panel, `px_basis` and the 16 placebos are free records
too: no intent, no seat, no charge, never reported by figure.

ONE CLOCK (section 1.2). The decision time tau of an auction (D, X) is 09:15:00 ET of D for O1 and D's close decision
time (close - 14 minutes) for ON. A decision of (D, X), live or catch-up, reads exactly: (a) rows STORED BEFORE tau (the
lane's items by `book._stored_before`, px_universe and the morning pass's values of D, `px_am`, written whole by
`morning` and serving an auction only when stored before its tau); (b) the rows ITS OWN RUN wrote after tau from raw
SIP 1Min bars whose bar end is at or before the value's knowable time (x_D and V_D: 15:30 ET, or close - 30 minutes;
pm_D: 08:59 ET), fetched inside the run because the Basic plan serves a bar 16 minutes after it ends; nothing else.
Every value is written ONCE into px.sqlite `px_features` (INSERT OR IGNORE) with the run's id, `decided_at` (the wall
time of the write), `as_of` (tau), `inputs_at` (the latest fetch time of its inputs) and `bar_end` (the latest bar end
of its inputs), under the kind of its run (`KIND_OF`: "on" / "o1" for a live run, "on@c" / "o1@c" for a catch-up), with
the live close run's `px1530` marks (`px_marks`, the run's id as their source) and every seat's and control's
selection (`px_decisions`); the deciding run of (D, X) is written once (px_meta `DECIDED_KEY`). A meta-learner reads
only THE LIVE PX RUN's rows (`live_features`, `live_selections`, `live_marks`: section 1.2 (c)); the hourly re-decision
reads the rows of the run that decided (D, X) (`redecide`: 1.2 (d)). A live run that did not finish leaves its rows
unread; its auction is decided later BY ITSELF (`decide`, kind "catchup", receipt `decide-px:<open|close>:<D>`), a
REPORTED SHADOW, NEVER A JUDGED BLOCK, NEVER TRADED and never a meta-learner's member.

THE RUNS' TIMES (section 4.6; league/events/house.py schedules them): the morning pass from 09:05 ET (it yields to every
other lane task and runs until 15:30: PXU(D) stored before 09:15 serves both auctions, later only the ON one); the
open run on the lane's open receipt, 60 s, never past 09:19:30 (`OPEN_BOUND`, `OPEN_UNTIL`); the close run from tau, no
read sent after tau + 45 s, each read's timeout min(45 s, tau + 50 s - now), its rows written only when every read
returned, ended by tau + 55 s (`CLOSE_LAST_REQUEST`, `CLOSE_READS_UNTIL`, `CLOSE_DONE`, `READ_CAP`).

CORPORATE ACTIONS (section 1.3). `morning` (`px-am:<D>`, after 09:00 ET of D) reads c*_P (P's adjustment=all close
read after 09:00 ET of D: league/events/pxdata.py `flags`, write-once in `px_flags`, the benchmarks' too), FLAGGED(D),
makes the full adjusted re-read of a name or benchmark FLAGGED at D, then of one FLAGGED on a session of its windows
after its latest full re-read (`px_rereads`; `reread_at`: the latest of those and the first night's 270-session read),
decides PXU(D) (px_universe's live base, then not FLAGGED(D), no FLAGGED session among the 61 before D without a full
re-read stored after its flag: `_basis_ok`, where a session with NO c*_P STORED BEFORE ITS DECISION TIME is FLAGGED,
section 1.1, as one out of the base that morning is) and writes every adjusted value of D once (`px_am`: sigma60,
sigma_on60 (the sample sd, n - 1, of the 60 returns ending at P), the records' z1, z5, z20, z1s, h52 (its 252 sessions
on one basis too, else none), v and the DRIFT values; a benchmark's closes on one basis with its cb*_P, else no value
that needs them). A catch-up reads `px_am` AS STORED BEFORE tau; with none there is no PX event of D at either
auction.

THE PX LANE NEVER CHANGES AN EARLIER PROGRAM'S RECORD (F10): it writes the lane's events.sqlite only for its own
programs' intents and its own receipts, and px.sqlite (its own px_* tables) for everything else; never the lane's
`eligibility`, `universe`, `bars` or `marks`."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import programs as P
from . import pxdata as PX
from . import pxstore as PS
from . import store as S
from . import universe as U

# ----------------------------------------------------------------------------------------------------- the constants
#: Section 3.1: the shadow's K a seat a session, the controls' 200, one event per issuer per D.
K = 40
CONTROL_N = 200
#: Section 3.1's rules.
Z_SEAT = 2.0
DROP_MOVE = (-0.35, -0.03)
SURGE_MOVE = (0.03, 0.20)
SURGE_VOLUME = 1.5
GAP_MOVE = (-0.35, -0.02)
GAP_MIN_ADV = 20_000_000.0
#: Section 1.1: FLAGGED's tolerance, the sessions of sigma60 and sigma_on60, the 52-week high's sessions, the volume
#: ratio's sessions, a SIC group's least size (z1s, zds).
FLAG_TOLERANCE = PS.FLAG_TOLERANCE
SIGMA_SESSIONS = 60
WINDOW_SESSIONS = PX.ADJUSTED_SESSIONS          # 61
HIGH_SESSIONS = 252
VOLUME_SESSIONS = 20
GROUP_MIN = 5
#: Section 3.3: the placebos (8 a window, 8 events a session each) and THE AUDIT's line.
PLACEBOS = 8
PLACEBO_EVENTS = 8
PLACEBO_ALARM = 3
#: Section 3.3: THE PINNED GRID (canonical: json.dumps(rows, sort_keys=True, separators=(",", ":"))).
GRID_SHA256 = "bb0d50e47d94e73f677a22bb612ef3f1cf7d23b23e5a51375fe965cf57e3e5a1"
GRID_FILE = Path(__file__).with_name("px_grid8.json")
#: Section 3.2 / 3.3: the six PREREG-EVL-1 to -4 controls whose issuers the DRIFT records follow, and their k's.
DRIFT_CONTROLS = ("EVL-CTRL-NEWS-ALL-O1", "EVL-CTRL-NEWS-DAY-ON", "EVL-CTRL-NEWSPM-ON", "EVL-CTRL-8K-ALL-O1",
                  "EVL-CTRL-8K-ON", "EVL-CTRL-ERN-ALL-O1")
DRIFT_KS = (1, 2, 3, 5)
#: The two auctions and their windows of records (section 3.3: O1 records are decided by the O1 run, ON and C1 records
#: by the ON run, which is D's close).
AUCTIONS = ("on", "o1")
WINDOWS_OF = {"on": ("ON", "C1"), "o1": ("O1",)}
#: The px_features kind of a run: the live run's, and a catch-up's (a cut live run's rows are never read).
KIND_OF = {("on", "live"): "on", ("on", "catchup"): "on@c", ("o1", "live"): "o1", ("o1", "catchup"): "o1@c"}
#: px_meta: the run that decided (D, X) ({run, kind, receipt, at}), written once at that run's end.
DECIDED_KEY = "px8:decided:{auction}:{day}"
#: px_meta: the morning pass of D done ({run, at, pxu}).
AM_KEY = "px8:am:{day}"
#: px_meta: the 09:30 opens of D read (OPENGAP's o_D).
MID_KEY = "px8:mid:{day}"
#: px_meta: the night's panel, record days and basis settled through a session.
PANEL_KEY = "px8:panel:{day}"
#: The receipts (the lane's store): the live runs and a catch-up.
JOB_LIVE = {"on": "decide-close-px8", "o1": "decide-open-px8"}
JOB_CATCHUP = "decide-px"
#: A catch-up's receipt names its auction as the lane's runs do: `decide-px:open:<D>`, `decide-px:close:<D>`.
AT_OF = {"o1": "open", "on": "close"}
JOB_AM = "px-am"
#: px_runs' job of release 1019i's 270-SESSION BACKFILL (league/events/house.py `_px_job` "backfill"): its read of an
#: issuer's adjusted bars is the issuer's first FULL re-read (section 1.3, `reread_at`).
BACKFILL_JOB = "backfill"
JOB_MID = "px-mid"
#: The lane's meta: PREREG-EVL-8's RELEASE, the moment the House's code carrying this file first ran its lane while it
#: registers anything (written once). A decision whose tau is before it was decided before the release: a catch-up.
RELEASE_KEY = "evl8:release"
#: The lane's meta: a run of this file FINISHED (section 4.6, the book's late passes BY TIME, league/events/book.py
#: `ready_8`): "open" once the House's open run `decide-open-px8:<D>` (its PX-GAP-O1 part, then its EVL-META-O1 part)
#: has ended whatever each part's end, "close-meta" once EVL-META-ON's part `decide-close-meta8:<D>` has.
RAN_KEY = "evl8:ran:{key}:{day}"
#: A catch-up's and a re-decision's why, as the intents keep it.
WHY_LIVE = "px8 live"
WHY_CATCHUP = "px8 catch-up (PREREG-EVL-8 section 3.4: a reported shadow, never judged, never traded)"
WHY_REMOVED = "skipped:stored-item"
#: Section 4.6's timing (ET wall times on a full day; an early close moves the close side by (close - 16:00)).
AM_AT = dt.time(9, 5)
AM_BUDGET = 300.0
#: The morning pass serves BOTH auctions of D only when PXU(D) is stored before 09:15:00 (the O1 tau); it yields to every
#: other lane task, resumes after the open decisions and runs until 15:30:00 (stored in [09:15, 15:30) it serves only
#: the ON auction; none by 15:30: no PX event of D).
AM_UNTIL = dt.time(15, 30)
MID_AT = dt.time(10, 0)
OPEN_BOUND = 60.0
OPEN_UNTIL = dt.time(9, 19, 30)
#: The close run (section 4.6): from tau, NO READ SENT after tau + 45 s, EACH READ'S TIMEOUT min(45 s, tau + 50 s - now)
#: (`READ_CAP`), its rows written only when every read returned, and ended by tau + 55 s (DECISION_MARGIN before the
#: lane's live close run at tau + 60 s, CLOSE_GRACE). The open run: 60 s from its start, never past 09:19:30 ET, each
#: read's timeout min(45 s, the bound - now).
CLOSE_LAST_REQUEST = dt.timedelta(seconds=45)
CLOSE_READS_UNTIL = dt.timedelta(seconds=50)
CLOSE_DONE = dt.timedelta(seconds=55)
READ_CAP = 45.0

SCHEMA_8 = """
CREATE TABLE IF NOT EXISTS px_am(day TEXT NOT NULL, cik TEXT NOT NULL, symbol TEXT NOT NULL, in_pxu INTEGER NOT NULL,
  why TEXT, value TEXT NOT NULL, decided_at TEXT NOT NULL, inputs_at TEXT, run TEXT NOT NULL, PRIMARY KEY(day, cik));
CREATE TABLE IF NOT EXISTS px_rereads(symbol TEXT NOT NULL, day TEXT NOT NULL, fetched_at TEXT NOT NULL,
  rows INTEGER NOT NULL, run TEXT NOT NULL, PRIMARY KEY(symbol, day));
CREATE TABLE IF NOT EXISTS px_decisions(run TEXT NOT NULL, auction TEXT NOT NULL, day TEXT NOT NULL,
  program TEXT NOT NULL, rank INTEGER NOT NULL, event TEXT NOT NULL, cik TEXT NOT NULL, symbol TEXT NOT NULL,
  rank_key REAL, adv20 REAL, prev_close REAL, PRIMARY KEY(run, program, rank));
CREATE TABLE IF NOT EXISTS px_panel(day TEXT NOT NULL, window TEXT NOT NULL, cik TEXT NOT NULL, symbol TEXT NOT NULL,
  entry_px REAL, exit_px REAL, bench TEXT, bench_entry REAL, bench_exit REAL, cost_entry_bp REAL, cost_exit_bp REAL,
  r REAL, b REAL, a REAL, status TEXT NOT NULL, settled_at TEXT NOT NULL, PRIMARY KEY(day, window, cik));
CREATE TABLE IF NOT EXISTS px_record_days(record TEXT NOT NULL, day TEXT NOT NULL, n INTEGER NOT NULL, sum_a REAL,
  sum_a2 REAL, sum_r REAL, written_at TEXT NOT NULL, PRIMARY KEY(record, day));
CREATE TABLE IF NOT EXISTS px_basis(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL, bar_r REAL,
  print_r REAL, bar_a REAL, print_a REAL, entry_gap_bp REAL, exit_gap_bp REAL, written_at TEXT NOT NULL,
  PRIMARY KEY(program, version, event));
CREATE TABLE IF NOT EXISTS px_marks(symbol TEXT NOT NULL, day TEXT NOT NULL, label TEXT NOT NULL, px REAL, t TEXT,
  source TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(symbol, day, label));
CREATE TABLE IF NOT EXISTS px_placebo(placebo TEXT NOT NULL, k INTEGER NOT NULL, blocks INTEGER, decision TEXT,
  passed INTEGER NOT NULL, p REAL, at TEXT NOT NULL, written_at TEXT NOT NULL, PRIMARY KEY(placebo, k));
"""
#: Every px.sqlite table this file adds (league/events/births.py `FACTS_DENY` refuses each, and the report's deny list).
TABLES_8 = frozenset({"px_am", "px_rereads", "px_decisions", "px_panel", "px_record_days", "px_basis", "px_marks",
                      "px_placebo"})
#: The columns this file adds to release 1019i's `px_features` (section 1.1's `as_of` and `bar_end`), additive.
FEATURE_COLUMNS = {"as_of": "ALTER TABLE px_features ADD COLUMN as_of TEXT",
                   "bar_end": "ALTER TABLE px_features ADD COLUMN bar_end TEXT"}


def _code_sha(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "unknown"


def release_id(path: Path | None = None) -> str | None:
    """The House release this code runs from (`<base>/releases/<id>/league/events/...`: league/watchdog.py's layout), or
    None off the House box. The deploy log maps the id to its commit (A121's recipe)."""
    here = Path(path or __file__).resolve()
    try:
        root = here.parents[2]
        return root.name if root.parent.name == "releases" else None
    except IndexError:
        return None


#: THE CODE'S IDENTITY (section 8: every catch-up is decided "by the release's code, whose commit sha each receipt
#: records"; PREREG-EVL-7's precedent: the sha256 of the file's own bytes, the release that carries it pinning its
#: commit): this file's sha256 and the House release it runs from, on every PX decision's receipt, live or catch-up.
CODE_SHA = _code_sha(Path(__file__))


def code_identity() -> dict[str, Any]:
    return {"code_sha": CODE_SHA, "release": release_id()}


class PxCutShort(Exception):
    """A decision run that could not finish inside its bound (its rows stay unread; a catch-up decides it later)."""


# ----------------------------------------------------------------------------------------------------- registry
def registered() -> bool:
    return P.registers_8()


def program(pid: str) -> P.Program8 | None:
    """This file's row of id `pid` in force (None while unpinned)."""
    return next((p for p in P.rows_8() if p.id == pid and p.px), None)


def seats(auction: str) -> list[P.Program8]:
    """The PX seats of an auction in force ("on": PX-DROP-ON, PX-SURGE-ON; "o1": PX-GAP-O1)."""
    at = "close" if auction == "on" else "open"
    return [p for p in P.rows_8() if p.px and p.seatable and p.entry_at == at]


def control(auction: str) -> P.Program8 | None:
    at = "close" if auction == "on" else "open"
    return next((p for p in P.rows_8() if p.px and not p.seatable and p.entry_at == at), None)


def auction_of(prog: Any) -> str:
    return "on" if getattr(prog, "entry_at", "") == "close" else "o1"


def event_id(prog: Any, day: dt.date, cik: str) -> str:
    """Section 3.1: `px:<program>:<D>:<cik>`."""
    return f"px:{getattr(prog, 'id', prog)}:{day.isoformat()}:{cik}"


def parse_event(event: str) -> tuple[str, dt.date, str] | None:
    """(program, D, cik) of a PX event id, None for any other."""
    m = re.fullmatch(r"px:([A-Z0-9-]+):(\d{4}-\d{2}-\d{2}):(\S+)", str(event))
    if m is None:
        return None
    return m.group(1), dt.date.fromisoformat(m.group(2)), m.group(3)


def knowable(session: C.Session, auction: str) -> dt.datetime:
    """Section 3.1's KNOWABLE TIME: 15:30 ET of D for the ON rows (close - 30 minutes on an early close), 08:59 ET for
    the O1 rows."""
    if auction == "on":
        return session.close_at - dt.timedelta(minutes=30)
    return session.at(dt.time(8, 59))


def event_knowable(store: Any, event: str) -> dt.datetime | None:
    """A PX event's knowable time from its id and the calendar (None for another id or a day the calendar lacks)."""
    got = parse_event(event)
    if got is None:
        return None
    prog = P.BY_KEY.get((got[0], 1)) or next((p for p in P.ROWS_8 if p.id == got[0]), None)
    session = C.session(store, got[1])
    if prog is None or session is None:
        return None
    return knowable(session, auction_of(prog))


def tau(session: C.Session, auction: str) -> dt.datetime:
    """Section 1.2's decision time: 09:15:00 ET of D (O1), D's close decision time (ON)."""
    return session.open_decide if auction == "o1" else session.close_decide


def spans(store: Any, day: dt.date) -> dict[str, tuple[dt.datetime, dt.datetime]]:
    """Section 1.1: THE ON SPAN of D, [P's close decision time, D's close decision time); THE O1 SPAN of D, [P's close
    decision time, 09:00 ET of D)."""
    d = C.session(store, day)
    prior = C.previous(store, day, 1)
    if d is None or not prior:
        raise LookupError(f"no session {day} or none before it")
    return {"on": (prior[-1].close_decide, d.close_decide), "o1": (prior[-1].close_decide, d.open_cutoff)}


# ----------------------------------------------------------------------------------------------------- the stores
def ensure(px: Any) -> None:
    """This file's px.sqlite tables (`SCHEMA_8`) and `px_features`' two columns, additive and idempotent (a release
    without this file never reads them)."""
    px.db.executescript(SCHEMA_8)
    have = {r[1] for r in px.db.execute("PRAGMA table_info(px_features)")}
    for col, ddl in FEATURE_COLUMNS.items():
        if col not in have:
            try:
                px.db.execute(ddl)
            except sqlite3.OperationalError as exc:      # (another process added it between the look and the ALTER)
                if "duplicate column" not in str(exc):
                    raise


def open_px(root: str | Path) -> PS.PxStore:
    """px.sqlite under the lane's root, with this file's tables."""
    px = PS.PxStore(root)
    ensure(px)
    return px


def read_only(root: str | Path) -> sqlite3.Connection | None:
    """px.sqlite opened READ-ONLY (the book's and the report's reads), None when there is none or it cannot be read."""
    path = PS.path_of(root)
    if not Path(path).is_file():
        return None
    try:
        db = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
        db.row_factory = sqlite3.Row
        db.execute("SELECT 1 FROM px_meta LIMIT 1")
        return db
    except sqlite3.Error:
        return None


def _meta(db: Any, key: str) -> str | None:
    try:
        row = db.execute("SELECT value FROM px_meta WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return None if row is None else str(row[0])


def _meta_json(db: Any, key: str) -> dict[str, Any] | None:
    raw = _meta(db, key)
    try:
        got = json.loads(raw) if raw else None
    except ValueError:
        return None
    return got if isinstance(got, dict) else None


def _set_once(db: Any, key: str, value: Mapping[str, Any]) -> bool:
    cur = db.execute("INSERT OR IGNORE INTO px_meta(key, value) VALUES(?, ?)", (key, json.dumps(dict(value),
                                                                                         sort_keys=True, default=str)))
    return cur.rowcount == 1


def decided(db: Any, day: dt.date, auction: str) -> dict[str, Any] | None:
    """The run that decided (D, X) ({run, kind, receipt, at}), None while none has."""
    return _meta_json(db, DECIDED_KEY.format(auction=auction, day=day.isoformat()))


# ----------------------------------------------------------------------------------------------------- the release
def release_at(store: Any) -> dt.datetime | None:
    """THE RELEASE (`RELEASE_KEY`): when the House's code carrying this file first ran its lane while it registers
    anything; None before (every decision is then before it: a catch-up, never traded or judged)."""
    try:
        raw = store.meta(RELEASE_KEY) if hasattr(store, "meta") else None
        return None if raw is None else S.parse_iso(str(raw))
    except Exception:  # noqa: BLE001 - an unreadable mark: before the release
        return None


def mark_release(store: S.Store, now: dt.datetime) -> dt.datetime | None:
    """Write THE RELEASE once (INSERT OR IGNORE) while this file registers anything; the mark on record."""
    if not registered():
        return None
    store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)", (RELEASE_KEY, S.iso(now)))
    return release_at(store)


def live_allowed(store: Any, session: C.Session, auction: str) -> bool:
    """Whether a decision of (D, X) may be live (traded, judged): this file registers, tau is after REGISTERED_AT_8 and
    at or after THE RELEASE (section 8: real money and every judged record start at the first decision after the
    release is live)."""
    if not registered():
        return False
    mark = release_at(store)
    at = tau(session, auction)
    return mark is not None and at >= mark and at > S.parse_iso(str(P.REGISTERED_AT_8))


# ----------------------------------------------------------------------------------------------------- the items
def item_ciks(store: Any, lo: dt.datetime, hi: dt.datetime, *, tickers: Mapping[str, Any],
              stored_by: dt.datetime | None = None) -> set[str]:
    """NO STORED ITEM's items (section 1.1), read with NO registration floor: the CIKs with (i) an ENEWS article of any
    source and any number of symbols whose symbols include a ticker SEC's copy (`tickers`, D's) maps to the CIK,
    PREREG-EVL-1 section 3's non-live exclusion applied; (ii) an 8-K (form exactly `8-K`, any items); (iii) a Form 4
    with PREREG-EVL-2's INSIDER BUY; each KNOWABLE IN [lo, hi). `stored_by` (a real-money decision): only items stored
    by then (`book._stored_before`: an article when read, a filing when its documents were fetched); None (the
    shadow's re-decision): whenever stored."""
    from . import book as EB

    def kept(row: Mapping[str, Any]) -> bool:
        try:
            at = S.parse_iso(str(row["knowable_at"]))
        except (KeyError, TypeError, ValueError):
            return False
        if not lo <= at < hi:
            return False
        return stored_by is None or EB._stored_before(row, stored_by, store)
    # news_named reads (lo, hi]; the span is [lo, hi): widen by one second and keep by `kept`
    articles = [a for a in P.news_named(store, lo - dt.timedelta(seconds=1), hi) if kept(a)]
    named = P.named_ciks(articles, P.ciks_by_ticker(tickers))
    filed = P.filed_ciks([r for r in P.filings_window(store, "8-K", lo, hi) if kept(r)])
    bought = P.bought_ciks([r for r in P.ins_buys_window(store, lo, hi) if kept(r)])
    return named | filed | bought


# ----------------------------------------------------------------------------------------------------- the morning
def _bars_between(px: Any, symbol: str, first: dt.date, last: dt.date, adj: str) -> dict[str, dict[str, Any]]:
    return {str(r["day"]): dict(r) for r in px.db.execute(
        "SELECT * FROM px_bars WHERE symbol=? AND adj=? AND day>=? AND day<=?",
        (symbol.upper(), adj, first.isoformat(), last.isoformat()))}


def _sd(xs: Sequence[float]) -> float | None:
    return statistics.stdev(xs) if len(xs) >= 2 else None


def _pos(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def reread_at(px: Any, symbol: str, now: dt.datetime) -> dt.datetime | None:
    """THE ISSUER'S LATEST FULL RE-READ stored before `now` (section 1.3): its latest `px_rereads` row (the full adjusted
    re-read the House makes after 09:00 ET of a session on which it is FLAGGED), else THE 270-SESSION READ OF THE FIRST
    NIGHT (league/events/pxdata.py `backfill`: the fetch time of its adjusted bars a `backfill` run wrote, the earliest
    of them, the reading that covers less), whichever is later; None with neither."""
    sym, stamp = symbol.upper(), S.iso(now)
    got = []
    row = px.db.execute("SELECT MAX(fetched_at) FROM px_rereads WHERE symbol=? AND fetched_at<?", (sym, stamp)).fetchone()
    if row is not None and row[0]:
        got.append(S.parse_iso(str(row[0])))
    row = px.db.execute("SELECT MIN(fetched_at) FROM px_bars WHERE symbol=? AND adj='all' AND fetched_at<? AND run IN "
                        "(SELECT run FROM px_runs WHERE job=?)", (sym, stamp, BACKFILL_JOB)).fetchone()
    if row is not None and row[0]:
        got.append(S.parse_iso(str(row[0])))
    return max(got) if got else None


def _basis_ok(px: Any, symbol: str, sessions: Sequence[C.Session], now: dt.datetime) -> str | None:
    """Section 1.3's ONE BASIS A WINDOW for `symbol` over `sessions` (a window before D: the 61 sessions, or h52's 252),
    read as stored before `now`: None when every session of it is CLEAR or COVERED, and every adjusted row of the
    window was fetched at or after the full re-read a COVERED session relies on; else why not (the issuer is not in
    PXU(D), or the value does not exist).
    - CLEAR: FLAGGED(s) is false: its `px_flags` row holds a c*_P read before s's last decision time (its close
      decision time) with |c*_P / c_P(raw) - 1| <= 0.001.
    - FLAGGED, section 1.1: a flagged row, OR NO c*_P STORED BEFORE THE DECISION TIME (no row, as for a session the
      issuer was out of the base, or one read too late): a split or a dividend effective s may be in the vendor's
      adjusted series and in no flag. Such a session is COVERED only by the issuer's latest full re-read (`reread_at`)
      fetched at or after its flag's read (with no row: at or after 09:00 ET of s, from when an action effective s is
      in the adjusted series); else the window mixes two bases."""
    if not sessions:
        return None
    sym = symbol.upper()
    want = [x.day.isoformat() for x in sessions]
    marks = ",".join("?" * len(want))
    flags = {str(r["day"]): dict(r) for r in px.db.execute(
        f"SELECT day, flagged, c_adj, read_at FROM px_flags WHERE symbol=? AND day IN ({marks}) AND read_at<?",
        (sym, *want, S.iso(now)))}
    latest = reread_at(px, sym, now)
    relied: dt.datetime | None = None
    for x in sessions:
        f = flags.get(x.day.isoformat())
        read = S.parse_iso(str(f["read_at"])) if f is not None else None
        if f is not None and not f["flagged"] and f["c_adj"] is not None and read < x.close_decide:
            continue
        since = read if f is not None and f["flagged"] else x.at(PX.FLAG_FROM)
        if latest is None or latest < since:
            if f is not None and f["flagged"]:
                return f"flagged {x.day.isoformat()} with no full re-read"
            return f"flagged {x.day.isoformat()} (no c*_P stored before its decision time) with no full re-read"
        relied = latest
    if relied is not None:
        old = px.db.execute(f"SELECT 1 FROM px_bars WHERE symbol=? AND adj='all' AND day IN ({marks}) AND fetched_at<? "
                            "LIMIT 1", (sym, *want, S.iso(relied))).fetchone()
        if old is not None:
            return "an adjusted bar older than its basis"
    return None


def _bench_basis(px: Any, symbol: str, flag: Mapping[str, Any] | None, sessions: Sequence[C.Session],
                 now: dt.datetime) -> str | None:
    """Section 1.3 for a BENCHMARK (cb, cb*_P: "the same for the issuer's benchmark"): its c*_P stored, its window on one
    basis (`_basis_ok`) and, when it is FLAGGED at D itself (an ETF's dividend), a full re-read stored after that flag's
    read with every adjusted row of the window fetched at or after it, so cb*_P and its closes share a basis; else why
    not (no value that needs it exists)."""
    if flag is None or flag.get("c_adj") is None:
        return "no benchmark c*_P stored"
    if flag.get("flagged"):
        latest = reread_at(px, symbol, now)
        if latest is None or latest < S.parse_iso(str(flag["read_at"])):
            return "flagged at D with no full re-read"
        want = [x.day.isoformat() for x in sessions]
        if want and px.db.execute(f"SELECT 1 FROM px_bars WHERE symbol=? AND adj='all' AND day IN ({','.join('?' * len(want))}) "
                                  "AND fetched_at<? LIMIT 1", (symbol.upper(), *want, S.iso(latest))).fetchone():
            return "an adjusted bar older than its basis"
    return _basis_ok(px, symbol, sessions, now)


def reread(px: Any, gw: Any, symbols: Iterable[str], calendar: Any, day: dt.date, *, now: dt.datetime, run: str,
           late: Callable[[], bool] | None = None) -> dict[str, int]:
    """Section 1.3's FULL ADJUSTED RE-READ of each symbol FLAGGED at `day` (after 09:00 ET of `day`): its
    adjustment=all daily bars of the `PX.BACKFILL_SESSIONS` sessions before `day`, written (px_bars' upsert keeps each
    moved close in px_bar_moves) and recorded once (`px_rereads`). Stops between symbols once `late()` says so."""
    prior = PX.sessions_before(calendar, day, PX.BACKFILL_SESSIONS)
    out = {"symbols": 0, "requests": 0, "rows": 0}
    if not prior:
        return out
    for sym in sorted({str(s).upper() for s in symbols}):
        if px.db.execute("SELECT 1 FROM px_rereads WHERE symbol=? AND day=?", (sym, day.isoformat())).fetchone():
            continue
        if late is not None and late():
            break
        got = PX.daily_bars(px, gw, [sym], prior[0].day, prior[-1].day, adj="all", now=now, run=run)
        px.db.execute("INSERT OR IGNORE INTO px_rereads(symbol, day, fetched_at, rows, run) VALUES(?, ?, ?, ?, ?)",
                      (sym, day.isoformat(), S.iso(now), int(got["rows"]), run))
        out["symbols"] += 1
        out["requests"] += got["requests"]
        out["rows"] += got["rows"]
    return out


def _flag(px: Any, day: dt.date, symbol: str, now: dt.datetime) -> dict[str, Any] | None:
    """FLAGGED(D)'s row of `symbol` READ AS STORED BEFORE `now` (None: no c*_P stored before the decision time)."""
    row = px.db.execute("SELECT * FROM px_flags WHERE day=? AND symbol=? AND read_at<?",
                        (day.isoformat(), symbol.upper(), S.iso(now))).fetchone()
    return None if row is None else dict(row)


def drift_events(store: Any, day: dt.date) -> dict[str, dict[str, dt.date]]:
    """The DRIFT records' events of D (section 3.3): {"<control>|<k>": {cik: E}} for each of the six PREREG-EVL-1 to -4
    controls and k in 1, 2, 3, 5: every issuer of an event of the control (an intent not skipped) whose exit session is
    the k-th session before D, the latest such event (its entry session, then the event id), E the session before that
    event's entry session."""
    back = C.previous(store, day, max(DRIFT_KS))
    out: dict[str, dict[str, dt.date]] = {}
    for k in DRIFT_KS:
        if len(back) < k:
            continue
        exit_day = back[-k].day
        for ctl in DRIFT_CONTROLS:
            got: dict[str, tuple[str, str]] = {}
            for r in store.db.execute("SELECT cik, entry_day, event FROM intents WHERE program=? AND version=1 AND "
                                      "exit_day=? AND status NOT LIKE 'skipped%' AND cik IS NOT NULL ORDER BY entry_day, "
                                      "event", (ctl, exit_day.isoformat())):
                got[str(r["cik"])] = (str(r["entry_day"]), str(r["event"]))
            rows = {}
            for cik, (entry, _) in got.items():
                before = C.previous(store, dt.date.fromisoformat(entry), 1)
                if before:
                    rows[cik] = before[-1].day
            out[f"{ctl}|{k}"] = rows
    return out


def morning(px: Any, store: Any, gw: Any, day: dt.date, *, now: dt.datetime, run: str,
            tickers: Mapping[str, Any] | None = None, assets: Mapping[str, Any] | None = None,
            late: Callable[[], bool] | None = None, clock: Callable[[], dt.datetime] | None = None) -> dict[str, Any]:
    """THE MORNING PASS OF D (`px-am:<D>`, section 4.6; after 09:00 ET of D, before either decision time): PXU(D)'s base
    (league/events/pxdata.py `universe`, write-once, when the 07:40 recorder has not written it and `tickers` and
    `assets` are given), c*_P and FLAGGED(D) of every base name and of both benchmarks (`pxdata.flags`), the full
    adjusted re-read of the names and benchmarks FLAGGED at D, then of those FLAGGED on a session of their windows (the
    61, h52's 252) after their latest full re-read (`reread`, while `late` lets it), then for every base name its
    `px_am` row, WRITE-ONCE: in or out of PXU(D) with why (`_basis_ok`), and its adjusted values (section 1.1, 1.3, 2
    and the records' texts). Returns its counts. Raises ValueError before 09:00 ET of D."""
    if not registered():
        return {"skipped": "PREREG-EVL-8 is not pinned"}
    session = C.session(store, day)
    if session is None:
        return {"skipped": "no session"}
    if now < session.at(PX.FLAG_FROM):
        raise ValueError(f"the morning pass of {day} reads c*_P after 09:00 ET of {day}")
    ensure(px)
    out: dict[str, Any] = {"day": day.isoformat()}
    base = px.universe(day)
    if not base and tickers is not None and assets is not None:
        out["universe"] = {k: v for k, v in PX.universe(px, store, day, tickers=tickers, assets=assets, now=now, run=run,
                                                        late=late).items() if k != "why"}
        base = px.universe(day)
    out["base"] = len(base)
    if not base:
        return out | {"why": "no PX universe base of the session"}
    names = sorted({str(r["symbol"]).upper() for r in base.values()})
    out["flags"] = PX.flags(px, gw, names + list(PX.BENCHMARKS), store, day, now=now, run=run)
    every = names + list(PX.BENCHMARKS)
    flagged = [s for s in every if (px.flag(day, s) or {}).get("flagged")]
    out["reread"] = reread(px, gw, flagged, store, day, now=now, run=run, late=late)
    prior = PX.sessions_before(store, day, max(HIGH_SESSIONS, WINDOW_SESSIONS) + 1)
    if len(prior) < WINDOW_SESSIONS:
        return out | {"why": "the calendar holds fewer than 61 sessions before it"}
    # SECTION 1.3: a name (or a benchmark) FLAGGED on a session of its windows (the 61, h52's 252) after its latest full
    # re-read, a session with no c*_P stored before its decision time among them (section 1.1), gets the full re-read
    # the House makes "after 09:00 ET of a session on which the issuer is FLAGGED, ... when it can": now, after the names
    # FLAGGED at D, while the pass may go on; one it cannot make leaves the name out of PXU(D) (`_basis_ok`).
    reach = prior[-HIGH_SESSIONS:]
    stamp = now + dt.timedelta(seconds=1)
    gapped = [s for s in every if s not in set(flagged) and _basis_ok(px, s, reach, stamp) is not None]
    out["reread_window"] = reread(px, gw, gapped, store, day, now=now, run=run, late=late)
    window = [s.day for s in prior[-WINDOW_SESSIONS:]]          # the 61 sessions before D, P last
    p_day = window[-1]
    sic: dict[str, str | None] = {str(r[0]): (str(r[1])[:2] if r[1] else None)
                                  for r in px.db.execute("SELECT cik, sic FROM cik_info")}
    bench: dict[str, dict[str, Any]] = {}
    for b in PX.BENCHMARKS:
        f = _flag(px, day, b, now + dt.timedelta(seconds=1))
        closes = _bars_between(px, b, prior[0].day, p_day, "all")
        # (section 1.3: the benchmark's closes in a value are on one basis too, cb*_P's: FLAGGED at D or a window
        # session FLAGGED with no full re-read, it has none, and no value that needs it exists)
        why = _bench_basis(px, b, f, prior[-WINDOW_SESSIONS:], stamp)
        bench[b] = {"c_star": _pos((f or {}).get("c_adj")) if why is None else None,
                    "closes": {d: _pos(r.get("c")) for d, r in closes.items()},
                    "why": None if why is None else f"benchmark {b}: {why}"}
    drift = drift_events(store, day)
    rows: dict[str, dict[str, Any]] = {}
    for cik, base_row in sorted(base.items()):
        if late is not None and late():
            # (PXU(D) is WRITTEN WHOLE AT ITS END, section 1.1: a pass cut here writes no row; its stored reads stay and
            # the next turn computes every row again from them)
            return out | {"left": len(base) - len(rows), "written": 0, "pxu": 0, "_status": "partial"}
        sym = str(base_row["symbol"]).upper()
        why, value = _am_value(px, sym, cik, base_row, day, prior, window, bench, drift, now)
        value["sic2"] = sic.get(str(cik))
        rows[cik] = {"symbol": sym, "why": why, "value": value}
    # z1s: the within-group mean of the one-session ratio over the PXU names of the issuer's SIC 2-digit group
    groups: dict[str, list[float]] = {}
    for cik, row in rows.items():
        v = row["value"]
        if row["why"] is None and v.get("sic2") and v.get("ratio1") is not None:
            groups.setdefault(str(v["sic2"]), []).append(float(v["ratio1"]))
    for cik, row in rows.items():
        v = row["value"]
        g = groups.get(str(v.get("sic2"))) if v.get("sic2") else None
        if row["why"] is None and g is not None and len(g) >= GROUP_MIN and v.get("ratio1") is not None and v.get("sigma60"):
            v["z1s"] = (float(v["ratio1"]) - math.fsum(g) / len(g)) / float(v["sigma60"])
        else:
            v["z1s"] = None
    written = inside = 0
    wrote = clock() if clock is not None else now     # (THE WRITE'S OWN TIME: the rows serve an auction only when
    stamp = S.iso(wrote)                              # stored before its tau, section 1.1)
    with px.tx() as db:
        for cik, row in rows.items():
            cur = db.execute("INSERT OR IGNORE INTO px_am(day, cik, symbol, in_pxu, why, value, decided_at, inputs_at, run) "
                             "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (day.isoformat(), str(cik), row["symbol"], int(row["why"] is None), row["why"],
                              json.dumps(row["value"], sort_keys=True), stamp, row["value"].get("inputs_at"), run))
            written += cur.rowcount
            inside += int(row["why"] is None and cur.rowcount == 1)
        _set_once(db, AM_KEY.format(day=day.isoformat()), {"run": run, "at": stamp, "pxu": inside,
                                                            "serves": "both" if wrote < session.open_decide else "on"})
    return out | {"written": written, "pxu": inside}


def _am_value(px: Any, sym: str, cik: str, base_row: Mapping[str, Any], day: dt.date, prior: Sequence[C.Session],
              window: Sequence[dt.date], bench: Mapping[str, Any], drift: Mapping[str, Mapping[str, dt.date]],
              now: dt.datetime) -> tuple[str | None, dict[str, Any]]:
    """One base name's morning values (`morning`): (why it is out of PXU(D), None when in; its values)."""
    value: dict[str, Any] = {"adv20": base_row.get("adv20"), "adv20sh": base_row.get("adv20sh"),
                             "prev_close": base_row.get("prev_close"), "bench": base_row.get("bench"),
                             "exchange": base_row.get("exchange")}
    f = _flag(px, day, sym, now + dt.timedelta(seconds=1))
    if f is None or f.get("c_adj") is None:
        return "flagged: no c*_P stored", value
    if f.get("flagged"):
        return "flagged", value
    why = _basis_ok(px, sym, prior[-WINDOW_SESSIONS:], now + dt.timedelta(seconds=1))
    if why is not None:
        return why, value
    b = str(base_row.get("bench") or "")
    bc = bench.get(b) or {}
    if bc.get("c_star") is None:
        return bc.get("why") or "no benchmark c*_P stored", value
    first = prior[0].day
    adj = _bars_between(px, sym, first, window[-1], "all")
    raw = _bars_between(px, sym, first, window[-1], "raw")
    closes = [_pos((adj.get(d.isoformat()) or {}).get("c")) for d in window]
    opens = [_pos((adj.get(d.isoformat()) or {}).get("o")) for d in window]
    if any(c is None for c in closes):
        return "adjusted-bars", value
    c_star = float(f["c_adj"])
    value.update(c_star=c_star, c_raw=_pos(f.get("c_raw")), cb_star=bc["c_star"])
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    value["sigma60"] = _sd(rets[-SIGMA_SESSIONS:])
    on = [opens[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if opens[i] is not None]
    value["sigma_on60"] = _sd(on[-SIGMA_SESSIONS:]) if len(on) >= SIGMA_SESSIONS else None
    sig = value["sigma60"]
    bcl = bc.get("closes") or {}

    def bench_close(d: dt.date) -> float | None:
        return bcl.get(d.isoformat())

    def zk(k: int) -> float | None:
        if not sig or len(window) < k + 1:
            return None
        ck, bk = closes[-1 - k], bench_close(window[-1 - k])
        if ck is None or bk is None:
            return None
        return (c_star / ck - bc["c_star"] / bk) / (sig * math.sqrt(k))
    value["z1"], value["z5"], value["z20"] = zk(1), zk(5), zk(20)
    value["ratio1"] = c_star / closes[-2] if closes[-2] else None
    # (h52 reads the 252 sessions' adjusted highs: on one basis too, section 1.3, else it does not exist)
    highs = [_pos((adj.get(s.day.isoformat()) or {}).get("h")) for s in prior[-HIGH_SESSIONS:]]
    value["h52"] = (c_star / max(highs)) if len(highs) == HIGH_SESSIONS and all(h is not None for h in highs) and \
        _basis_ok(px, sym, prior[-HIGH_SESSIONS:], now + dt.timedelta(seconds=1)) is None else None
    vols = [_pos((raw.get(d.isoformat()) or {}).get("v")) for d in window[-(VOLUME_SESSIONS + 1):]]
    value["v"] = (vols[-1] / (math.fsum(vols[:-1]) / VOLUME_SESSIONS)
                  if len(vols) == VOLUME_SESSIONS + 1 and all(x is not None for x in vols) else None)
    zs: dict[str, float] = {}
    for key, issuers in drift.items():
        e = issuers.get(str(cik))
        if e is None or not sig:
            continue
        ce = _pos((adj.get(e.isoformat()) or {}).get("c"))
        be = bench_close(e)
        n = sum(1 for d in window if d > e)
        if ce is None or be is None or n < 1:
            continue
        zs[key] = (c_star / ce - bc["c_star"] / be) / (sig * math.sqrt(n))
    value["drift"] = zs
    fetched = [str(r["fetched_at"]) for r in list(adj.values()) + list(raw.values())]
    value["inputs_at"] = max(fetched + [str(f["read_at"])]) if fetched else str(f["read_at"])
    if sig is None:
        return "no sigma60", value
    return None, value


def pxu(db: Any, day: dt.date, *, before: dt.datetime | None = None) -> dict[str, dict[str, Any]]:
    """PXU(D) as the morning pass wrote it ({cik: {symbol, value...}}), its rows stored before `before` when given."""
    sql, args = "SELECT * FROM px_am WHERE day=? AND in_pxu=1", [day.isoformat()]
    if before is not None:
        sql += " AND decided_at<?"
        args.append(S.iso(before))
    out = {}
    for r in db.execute(sql, args):
        v = json.loads(r["value"])
        out[str(r["cik"])] = {"symbol": str(r["symbol"]), **v}
    return out


def mid(px: Any, gw: Any, store: Any, day: dt.date, *, now: dt.datetime, run: str) -> dict[str, Any]:
    """THE 09:30 OPENS OF D (`px-mid:<D>`, section 3.3's OPENGAP; from 10:00 ET): the open of the raw SIP 1Min bar
    starting at 09:30:00 ET of every PXU(D) name and both benchmarks, write-once in px_minutes (`o0930`), so the ON run
    reads them as stored before tau."""
    if not registered():
        return {"skipped": "PREREG-EVL-8 is not pinned"}
    session = C.session(store, day)
    if session is None:
        return {"skipped": "no session"}
    ensure(px)
    names = sorted({str(v["symbol"]) for v in pxu(px.db, day).values()} | set(PX.BENCHMARKS))
    got = PX.minutes(px, gw, names, session, "o0930", now=now, run=run)
    if not got.get("waiting"):
        _set_once(px.db, MID_KEY.format(day=day.isoformat()), {"run": run, "at": S.iso(now)})
    return got


# ----------------------------------------------------------------------------------------------------- the values
def _minute_value(bars: Sequence[Mapping[str, Any]], label: str) -> tuple[float | None, str | None, str | None]:
    """(value, first bar time, last bar END) of a span's bars (`PX.minutes`' rules)."""
    if not bars:
        return None, None, None
    end = S.iso(S.parse_iso(str(bars[-1]["t"])) + dt.timedelta(minutes=1))
    value = {"px1530": PX.last_close, "pm": PX.pm_value, "v1530": PX.volume}[label](bars)
    return value, str(bars[0]["t"]), end


def read_minutes(gw: Any, symbols: Sequence[str], session: C.Session, label: str, *,
                 now: dt.datetime) -> dict[str, tuple[float | None, str | None, str | None]] | None:
    """The run's OWN READ (section 1.2 (b)) of a minute value of `symbols`: {symbol: (value, first bar, bar end)} from
    raw SIP 1Min bars of the value's span (`PX.span_1530`, `span_pm`, `span_v1530`), every bar ending by the value's
    knowable time; None while the span is not whole on the Basic plan's tape."""
    span = {"px1530": lambda: PX.span_1530(session), "pm": lambda: PX.span_pm(session.day),
            "v1530": lambda: PX.span_v1530(session)}[label]()
    got = PX.minute_bars(gw, sorted({s.upper() for s in symbols}), span[0], span[1], now=now)
    if got is None:
        return None
    return {sym: _minute_value(PX._in(bars, *span), label) for sym, bars in got.items()}


def values_on(am: Mapping[str, Mapping[str, Any]], items: set[str], x: Mapping[str, tuple], vd: Mapping[str, tuple],
              opens: Mapping[str, float | None]) -> dict[str, dict[str, Any]]:
    """THE ON RUN'S VALUES of every PXU(D) name (section 2 and the ON and C1 records' texts): `am` the morning rows,
    `items` the names with a stored item in the ON span (x_D is read only for the others: section 3.1's READS), `x` the
    px1530 reads by symbol (benchmarks included), `vd` the volume reads, `opens` the stored 09:30 opens by symbol."""
    out: dict[str, dict[str, Any]] = {}
    xr: dict[str, float] = {}
    for cik, a in am.items():
        sym = str(a["symbol"])
        news = cik in items
        val: dict[str, Any] = {k: a.get(k) for k in ("adv20", "adv20sh", "prev_close", "bench", "exchange", "sigma60",
                                                     "sigma_on60", "c_star", "cb_star", "sic2", "z1", "z5", "z20",
                                                     "z1s", "h52", "v")}
        val["news"] = int(news)
        bench = str(a.get("bench") or "")
        xv = None if news else (x.get(sym) or (None,))[0]
        xb = (x.get(bench) or (None,))[0]
        sig, c_star, cb = a.get("sigma60"), a.get("c_star"), a.get("cb_star")
        val["x"] = xv
        if xv is not None and xb is not None and sig and c_star and cb:
            val["move_d"] = xv / c_star - 1.0
            val["zd"] = (xv / c_star - xb / cb) / sig
            xr[cik] = xv / c_star
        else:
            val["move_d"] = val["zd"] = None
        vv = (vd.get(sym) or (None,))[0]
        val["vd"] = (vv / float(a["adv20sh"])) if vv is not None and a.get("adv20sh") else None
        od, ob = opens.get(sym), opens.get(bench)
        val["zo"] = ((od / c_star - ob / cb) / sig) if od and ob and sig and c_star and cb else None
        out[cik] = val
    groups: dict[str, list[float]] = {}
    for cik, r in xr.items():
        g = out[cik].get("sic2")
        if g:
            groups.setdefault(str(g), []).append(r)
    for cik, val in out.items():
        g = groups.get(str(val.get("sic2"))) if val.get("sic2") else None
        r = xr.get(cik)
        val["zds"] = ((r - math.fsum(g) / len(g)) / float(val["sigma60"])
                      if r is not None and g is not None and len(g) >= GROUP_MIN and val.get("sigma60") else None)
    return out


def values_o1(am: Mapping[str, Mapping[str, Any]], items: set[str], pm: Mapping[str, tuple]) -> dict[str, dict[str, Any]]:
    """THE O1 RUN'S VALUES of every PXU(D) name (section 2 and the O1 records' texts): `items` the names with a stored
    item in the O1 span (pm_D is read only for PX-GAP-O1's events-of-D population), `pm` the premarket reads."""
    out: dict[str, dict[str, Any]] = {}
    for cik, a in am.items():
        sym = str(a["symbol"])
        news = cik in items
        val: dict[str, Any] = {k: a.get(k) for k in ("adv20", "adv20sh", "prev_close", "bench", "exchange", "sigma60",
                                                     "sigma_on60", "c_star", "cb_star", "sic2", "z1", "z5", "z20",
                                                     "z1s", "h52", "v")}
        val["news"] = int(news)
        val["drift"] = dict(a.get("drift") or {})
        bench = str(a.get("bench") or "")
        gap_pop = not news and float(a.get("adv20") or 0) >= GAP_MIN_ADV
        pv = (pm.get(sym) or (None,))[0] if gap_pop else None
        pb = (pm.get(bench) or (None,))[0]
        sig, c_star, cb = a.get("sigma_on60"), a.get("c_star"), a.get("cb_star")
        val["pm"] = pv
        val["gap_pop"] = int(gap_pop)
        if pv is not None and pb is not None and sig and c_star and cb:
            val["move_g"] = pv / c_star - 1.0
            val["zg"] = (pv / c_star - pb / cb) / sig
        else:
            val["move_g"] = val["zg"] = None
        out[cik] = val
    return out


# ----------------------------------------------------------------------------------------------------- the seats
def qualifies(prog: Any, v: Mapping[str, Any]) -> float | None:
    """Section 3.1's rule of seat `prog` on one name's values: its rank_key (higher first) when it qualifies, else
    None. The events of D: the ON seats' a PXU(D) name with no stored item in the ON span; PX-GAP-O1's one with ADV20 >=
    $20,000,000 and no stored item in the O1 span."""
    pid = getattr(prog, "id", prog)
    if v.get("news"):
        return None
    if pid == "PX-DROP-ON":
        zd, mv = v.get("zd"), v.get("move_d")
        if zd is not None and mv is not None and zd <= -Z_SEAT and DROP_MOVE[0] <= mv <= DROP_MOVE[1]:
            return -float(zd)
    elif pid == "PX-SURGE-ON":
        zd, mv, vd = v.get("zd"), v.get("move_d"), v.get("vd")
        if zd is not None and mv is not None and vd is not None and zd >= Z_SEAT and SURGE_MOVE[0] <= mv <= SURGE_MOVE[1] \
                and vd >= SURGE_VOLUME:
            return float(zd)
    elif pid == "PX-GAP-O1":
        zg, mg = v.get("zg"), v.get("move_g")
        if float(v.get("adv20") or 0) >= GAP_MIN_ADV and zg is not None and mg is not None and zg <= -Z_SEAT and \
                GAP_MOVE[0] <= mg <= GAP_MOVE[1]:
            return -float(zg)
    return None


def ranked(prog: Any, values: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, float]]:
    """The seat's qualifying names in its ranking (section 3.1): rank_key descending, then ADV20 descending, then CIK."""
    got = [(cik, rk) for cik, v in values.items() for rk in [qualifies(prog, v)] if rk is not None]
    return sorted(got, key=lambda x: (-x[1], -float(values[x[0]].get("adv20") or 0.0), x[0]))


def control_population(auction: str, values: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Section 3.2's populations: CTRL-PX-ALL-ON's, the PXU(D) names with no stored item in the ON span; CTRL-PX-ALL-O1's,
    PX-GAP-O1's events-of-D population (ADV20 >= $20,000,000, no stored item in the O1 span)."""
    if auction == "on":
        return [cik for cik, v in values.items() if not v.get("news")]
    return [cik for cik, v in values.items() if not v.get("news") and float(v.get("adv20") or 0) >= GAP_MIN_ADV]


def control_hash(auction: str, day: dt.date, cik: str) -> str:
    """sha256("PX-CTRL|ON|<D>|<cik>") (or "|O1|"), lower-case hex, compared as text."""
    return hashlib.sha256(f"PX-CTRL|{auction.upper()}|{day.isoformat()}|{cik}".encode()).hexdigest()


def placebo_hash(window: str, j: int, day: dt.date, cik: str) -> str:
    """sha256("PX-PLACEBO|<window>|<j>|<D>|<cik>")."""
    return hashlib.sha256(f"PX-PLACEBO|{window}|{int(j)}|{day.isoformat()}|{cik}".encode()).hexdigest()


def take(store: Any, prog: Any, day: dt.date, order: Sequence[str], n: int) -> tuple[list[str], list[str]]:
    """The first `n` names of `order` the program does not skip under PREREG-EVL-1 section 5's one position per issuer
    as A72 reads it (league/events/programs.py `_held_recently`: held, held within the last 5 sessions, or an intent
    entering within the 5 sessions after), and the skipped names ranked before the last taken."""
    got: list[str] = []
    skipped: list[str] = []
    for cik in order:
        if len(got) >= n:
            break
        if P._held_recently(store, prog, cik, day):
            skipped.append(cik)
            continue
        got.append(cik)
    return got, skipped


def write_rows(store: S.Store, prog: Any, day: dt.date, ciks: Sequence[str], values: Mapping[str, Mapping[str, Any]],
               *, ranks: Mapping[str, float | None], decided_at: dt.datetime, why: str, held: Sequence[str] = ()
               ) -> dict[str, int]:
    """One intent per name of `ciks` (planned) and of `held` (skipped:issuer-held), idempotent per event (league/events/
    programs.py `write_intents`, the lane's own writer): event `px:<program>:<D>:<cik>`, the PXU symbol, rank_key the
    seat's (None for a control), decided at tau."""
    session = C.session(store, day)
    at = knowable(session, auction_of(prog)) if session is not None else decided_at
    cands = [P.Candidate(event_id(prog, day, cik), cik, str(values[cik].get("symbol") or values[cik].get("sym") or ""),
                         at, ranks.get(cik), None, {}) for cik in [*ciks, *held]]
    return P.write_intents(store, prog, day, cands, decided_at=decided_at, why=why)


# ----------------------------------------------------------------------------------------------------- the decisions
def decide(px: Any, store: S.Store, gw: Any, day: dt.date, auction: str, *, now: Callable[[], dt.datetime],
           kind: str = "live", tickers: Mapping[str, Any] | None = None, late: Callable[[], bool] | None = None
           ) -> dict[str, Any]:
    """ONE PX DECISION OF (D, X) (section 3.4), BY ITSELF: `kind` "live" (`decide-close-px8:<D>` from tau, or
    `decide-open-px8:<D>` on the lane's open receipt) or "catchup" (`decide-px:<open|close>:<D>`, an auction no live run
    decided;
    never judged, never traded). It reads PXU(D) and the morning values as stored before tau, the items stored before
    tau (`item_ciks`), and its own minute reads (section 1.2 (b)); writes every name's values once into `px_features`
    under its run's kind, its seats' and control's intents (K 40 each after A72's skips; the control's 200), its ranked
    picks (`px_decisions`, the book's), its receipt, and LAST the deciding run of (D, X) (`DECIDED_KEY`). A run cut
    before its end (`late`, a PX read refused: `PxCut`) writes no decision mark and no receipt `ok`: nothing of it is
    read; a catch-up decides the auction later. Returns its summary (counts only)."""
    if not registered():
        return {"skipped": "PREREG-EVL-8 is not pinned"}
    session = C.session(store, day)
    if session is None:
        return {"skipped": "no session"}
    ensure(px)
    t = tau(session, auction)
    if decided(px.db, day, auction) is not None:
        return {"skipped": f"({day.isoformat()}, {auction}) is decided already"}
    if kind == "live" and not live_allowed(store, session, auction):
        return {"skipped": "not live: before the release or the registration (a catch-up decides it)"}
    started = now()
    if started < t:
        raise ValueError(f"a PX decision of {day} {auction} runs at or after its tau {S.iso(t)}")
    job = f"{JOB_LIVE[auction]}:{day.isoformat()}" if kind == "live" else \
        f"{JOB_CATCHUP}:{AT_OF[auction]}:{day.isoformat()}"
    rid = store.start_receipt(job, now=started)
    run = px.start_run(JOB_LIVE[auction] if kind == "live" else JOB_CATCHUP, now=started)
    out: dict[str, Any] = {"day": day.isoformat(), "auction": auction, "kind": kind, "run": run, **code_identity()}
    try:
        got = _decide(px, store, gw, session, auction, t, now=now, kind=kind, run=run, tickers=tickers, late=late)
    except (PX.PxCut, PxCutShort) as exc:
        px.finish_run(run, "cut", now=now(), summary={"cut": str(exc)[:200]})
        store.finish_receipt(rid, "cut", out | {"cut": str(exc)[:200]}, now=now())
        return out | {"_status": "cut", "cut": str(exc)[:200]}
    except Exception as exc:  # noqa: BLE001 - the run's failure is its own: a catch-up decides the auction later
        px.finish_run(run, "failed", now=now(), summary={"error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        store.finish_receipt(rid, "failed", out | {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, now=now())
        return out | {"_status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    out.update(got)
    end = now()
    if late is not None and late():
        px.finish_run(run, "cut", now=end, summary={"cut": "the run's bound passed before its end"})
        store.finish_receipt(rid, "cut", out | {"cut": "the run's bound passed before its end"}, now=end)
        return out | {"_status": "cut"}
    with px.tx() as db:
        _set_once(db, DECIDED_KEY.format(auction=auction, day=day.isoformat()),
                  {"run": run, "kind": kind, "receipt": rid, "at": S.iso(end)})
    px.finish_run(run, "ok", now=end, summary={k: v for k, v in out.items() if isinstance(v, (int, str))})
    store.finish_receipt(rid, "ok", out, now=end)
    return out | {"_status": "ok"}


def _decide(px: Any, store: S.Store, gw: Any, session: C.Session, auction: str, t: dt.datetime, *,
            now: Callable[[], dt.datetime], kind: str, run: str, tickers: Mapping[str, Any] | None,
            late: Callable[[], bool] | None) -> dict[str, Any]:
    day = session.day
    am = pxu(px.db, day, before=t)
    out: dict[str, Any] = {"pxu": len(am)}
    if not am:
        return out | {"why": "no PXU(D) stored before tau: no PX event of the session"}
    if tickers is None:
        from . import book as EB
        tickers = EB.lane_tickers(store, day)
    lo, hi = spans(store, day)[auction]
    items = item_ciks(store, lo, hi, tickers=tickers, stored_by=t) & set(am)
    out["items"] = len(items)
    benches = sorted(set(PX.BENCHMARKS))
    if auction == "on":
        names = sorted({str(a["symbol"]) for c, a in am.items() if c not in items} | set(benches))
        x = read_minutes(gw, names, session, "px1530", now=now())
        if x is None:
            raise PxCutShort("the 15:30 bars are not on the tape yet")
        first = values_on(am, items, x, {}, {})
        surge = sorted({str(am[c]["symbol"]) for c, v in first.items() if v.get("zd") is not None and v["zd"] >= Z_SEAT})
        vd = read_minutes(gw, surge, session, "v1530", now=now()) if surge else {}
        if vd is None:
            raise PxCutShort("the session's minute volumes are not on the tape yet")
        opens = {}
        for r in px.db.execute("SELECT symbol, value FROM px_minutes WHERE day=? AND label='o0930' AND fetched_at<?",
                               (day.isoformat(), S.iso(t))):
            opens[str(r["symbol"])] = _pos(r["value"])
        values = values_on(am, items, x, vd, opens)
        reads = {"x": x, "vd": vd}
    else:
        names = sorted({str(a["symbol"]) for c, a in am.items()
                        if c not in items and float(a.get("adv20") or 0) >= GAP_MIN_ADV} | set(benches))
        pm = read_minutes(gw, names, session, "pm", now=now())
        if pm is None:
            raise PxCutShort("the premarket bars are not on the tape yet")
        values = values_o1(am, items, pm)
        reads = {"pm": pm}
    if late is not None and late():
        raise PxCutShort("the run's bound passed")
    stamp = now()
    feature_kind = KIND_OF[(auction, kind)]
    inputs_at = S.iso(stamp)
    rows = []
    for cik, v in values.items():
        sym = str(am[cik]["symbol"])
        v["symbol"] = sym
        ends = [e for r in reads.values() for e in [(r.get(sym) or (None, None, None))[2]] if e]
        rows.append((day.isoformat(), cik, feature_kind, sym, json.dumps(v, sort_keys=True), S.iso(stamp), inputs_at,
                     None, max(ends) if ends else None, "live", run, S.iso(t), max(ends) if ends else None))
    marks = []
    if auction == "on":     # (THE PX1530 MARKS of D, section 7.2's THE MARKS: written by this run, with its id)
        for sym, (value, _, end) in sorted((reads.get("x") or {}).items()):
            if value is not None and end:
                marks.append((sym, day.isoformat(), "px1530", float(value),
                              S.iso(S.parse_iso(end) - dt.timedelta(minutes=1)), run, S.iso(stamp)))
    with px.tx() as db:
        for row in rows:
            db.execute("INSERT OR IGNORE INTO px_features(day, cik, kind, symbol, value, decided_at, inputs_at, bars_from, "
                       "bars_to, source, run, as_of, bar_end) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
        for row in marks:
            db.execute("INSERT OR IGNORE INTO px_marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, ?, ?, ?, "
                       "?, ?)", row)
    out["features"] = len(rows)
    why = WHY_LIVE if kind == "live" else WHY_CATCHUP
    counts: dict[str, Any] = {}
    with store.tx():
        for prog in seats(auction):
            order = [cik for cik, _ in ranked(prog, values)]
            got, held = take(store, prog, day, order, K)
            ranks = dict(ranked(prog, values))
            counts[prog.id] = {"qualifying": len(order), **write_rows(store, prog, day, got, values, ranks=ranks,
                                                                       decided_at=t, why=why, held=held)}
            with px.tx() as db:
                for n, cik in enumerate(got, 1):
                    db.execute("INSERT OR IGNORE INTO px_decisions(run, auction, day, program, rank, event, cik, symbol, "
                               "rank_key, adv20, prev_close) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (run, auction, day.isoformat(), prog.id, n, event_id(prog, day, cik), cik,
                                values[cik]["symbol"], ranks[cik], values[cik].get("adv20"),
                                values[cik].get("prev_close")))
        ctl = control(auction)
        if ctl is not None:
            pop = sorted(control_population(auction, values), key=lambda c: control_hash(auction, day, c))
            got, _ = take(store, ctl, day, pop, CONTROL_N)
            counts[ctl.id] = write_rows(store, ctl, day, got, values, ranks={}, decided_at=t, why=why)
            with px.tx() as db:     # (the control's selection by this run: section 7.2's members of the live PX run)
                for n, cik in enumerate(got, 1):
                    db.execute("INSERT OR IGNORE INTO px_decisions(run, auction, day, program, rank, event, cik, symbol, "
                               "rank_key, adv20, prev_close) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (run, auction, day.isoformat(), ctl.id, n, event_id(ctl, day, cik), cik,
                                values[cik]["symbol"], None, values[cik].get("adv20"), values[cik].get("prev_close")))
    out["programs"] = counts
    return out


def redecide(px: Any, store: S.Store, day: dt.date, auction: str, *, now: dt.datetime,
             tickers: Mapping[str, Any] | None = None, keep: Callable[[Any], bool] | None = None) -> dict[str, Any]:
    """THE LANE'S HOURLY RE-DECISION OF THE PX ROWS of (D, X) (section 3.4, section 1.2 (d)), shadow only: the seats'
    K 40 and the control's 200 re-taken from the stored px_features of THE PX RUN THAT DECIDED (D, X) (the live run,
    else its `decide-px` catch-up; never recomputed, never written again) under the shadow's NO STORED ITEM reading (an
    item knowable in the span, whenever stored, removes its issuer: its unsettled intent moves to `skipped:stored-item`,
    and the next qualifying name in the stored ranking takes its place). Never a meta-learner's (its decision is written
    once, and its members read the live run's selections at tau, `px_decisions`, never these), never a program `keep`
    holds (a written look of it covering D). Returns {program: {removed, added}}."""
    if not registered():
        return {}
    got = decided(px.db, day, auction)
    if got is None:
        return {}
    if tickers is None:
        from . import book as EB
        tickers = EB.lane_tickers(store, day)
    lo, hi = spans(store, day)[auction]
    kind = KIND_OF[(auction, "live" if got.get("kind") == "live" else "catchup")]
    why = WHY_LIVE if got.get("kind") == "live" else WHY_CATCHUP
    values = {str(r["cik"]): json.loads(r["value"]) for r in px.db.execute(
        "SELECT cik, value FROM px_features WHERE day=? AND kind=? AND run=?", (day.isoformat(), kind, got["run"]))}
    if not values:
        return {}
    late = item_ciks(store, lo, hi, tickers=tickers) & set(values)
    session = C.session(store, day)
    t = tau(session, auction)
    out: dict[str, Any] = {}
    progs = [*seats(auction)] + ([control(auction)] if control(auction) else [])
    with store.tx():
        for prog in progs:
            if keep is not None and keep(prog):
                continue
            have = {str(r["cik"]): str(r["status"]) for r in store.db.execute(
                "SELECT cik, status FROM intents WHERE program=? AND version=? AND entry_day=?",
                (prog.id, prog.version, day.isoformat()))}
            removed = 0
            for cik in sorted(late):
                if have.get(cik) in ("planned", "entered") and \
                        store.move_intent(prog.id, prog.version, event_id(prog, day, cik), WHY_REMOVED,
                                          "an item knowable in the span, stored after the decision"):
                    removed += 1
            live_vals = {c: (v | {"news": 1}) if c in late else v for c, v in values.items()}
            standing = {c for c, s in have.items() if s in ("planned", "entered", "exited")}
            if prog.seatable:
                order = [c for c, _ in ranked(prog, live_vals)]
                ranks = dict(ranked(prog, live_vals))
                n = K
            else:
                order = sorted(control_population(auction, live_vals), key=lambda c: control_hash(auction, day, c))
                ranks, n = {}, CONTROL_N
            want: list[str] = []
            for cik in order:
                if len(want) >= n:
                    break
                if cik in standing or cik in have:
                    if cik in standing:
                        want.append(cik)
                    continue
                if P._held_recently(store, prog, cik, day):
                    continue
                want.append(cik)
            new = [c for c in want if c not in have]
            added = write_rows(store, prog, day, new, values, ranks=ranks, decided_at=t, why=why)["planned"] \
                if new else 0
            out[prog.id] = {"removed": removed, "added": added}
    return out


def live_picks(db: Any, prog: Any, day: dt.date) -> list[dict[str, Any]]:
    """THE REAL-MONEY PICKS OF A PX SEAT for D (section 4): its ranked names of the LIVE run that decided its auction
    (`px_decisions`; none when a catch-up decided it, or none did), in rank order, each {event, cik, symbol, rank_key,
    adv20, prev_close}."""
    auction = auction_of(prog)
    got = decided(db, day, auction)
    if got is None or got.get("kind") != "live":
        return []
    return [dict(r) for r in db.execute("SELECT * FROM px_decisions WHERE run=? AND program=? AND day=? ORDER BY rank",
                                        (got["run"], getattr(prog, "id", prog), day.isoformat()))]


def live_run(db: Any, day: dt.date, auction: str) -> str | None:
    """THE LIVE PX RUN OF (D, X) (section 1.2 (c)): the run id of `decide-close-px8:<D>` (X = ON) or of the PX-GAP-O1
    part of `decide-open-px8:<D>` (X = O1) when it finished and wrote its px_features (the deciding mark, kind live);
    None otherwise (no catch-up is ever a meta-learner's PX run)."""
    got = decided(db, day, auction)
    return None if got is None or got.get("kind") != "live" else str(got["run"])


def live_features(db: Any, day: dt.date, auction: str) -> dict[str, dict[str, Any]]:
    """The px_features rows of THE LIVE PX RUN OF (D, X) ({cik: values}): a meta-learner's `x:` experts and PX
    members read these only (section 7.3); {} with no live run."""
    run = live_run(db, day, auction)
    if run is None:
        return {}
    return {str(r["cik"]): json.loads(r["value"]) for r in db.execute(
        "SELECT cik, value FROM px_features WHERE day=? AND kind=? AND run=?",
        (day.isoformat(), KIND_OF[(auction, "live")], run))}


def live_selections(db: Any, day: dt.date, auction: str) -> dict[str, list[dict[str, Any]]]:
    """{program: the names THE LIVE PX RUN OF (D, X) selected, in its order} for its seats (K 40) and its control (200)
    (`px_decisions`: the intents that run wrote, never the hourly re-decision's); {} with no live run (section 7.2)."""
    run = live_run(db, day, auction)
    if run is None:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for r in db.execute("SELECT * FROM px_decisions WHERE run=? AND day=? ORDER BY program, rank", (run, day.isoformat())):
        out.setdefault(str(r["program"]), []).append(dict(r))
    return out


def live_marks(db: Any, day: dt.date) -> dict[str, dict[str, Any]]:
    """D's `px1530` marks as THE LIVE PX RUN OF (D, ON) wrote them ({symbol: {px, t, fetched_at}}; section 7.2's THE
    MARKS); {} with no live run."""
    run = live_run(db, day, "on")
    if run is None:
        return {}
    return {str(r["symbol"]).upper(): dict(r) for r in db.execute(
        "SELECT * FROM px_marks WHERE day=? AND label='px1530' AND source=?", (day.isoformat(), run))}


def universe_row(db: Any, day: dt.date, cik: str) -> dict[str, Any] | None:
    """px_universe's LIVE row of (D, CIK) (section 4.4: a PX seat's eligibility, prev_close and adv20), None when none."""
    try:
        row = db.execute("SELECT * FROM px_universe WHERE day=? AND cik=? AND rule=?",
                         (day.isoformat(), str(cik), S.LIVE_RULE)).fetchone()
    except sqlite3.Error:
        return None
    return None if row is None else dict(row)


def judged_days(db: Any, auction: str) -> set[str]:
    """The entry sessions of an auction a LIVE run decided (their intents are a seat's judged record; a catch-up's never
    are)."""
    out = set()
    prefix = f"px8:decided:{auction}:"
    for r in db.execute("SELECT key, value FROM px_meta WHERE key LIKE ?", (prefix + "%",)):
        try:
            if json.loads(r["value"]).get("kind") == "live":
                out.add(str(r["key"])[len(prefix):])
        except (TypeError, ValueError):
            continue
    return out


def features(db: Any, day: dt.date, auction: str) -> dict[str, dict[str, Any]]:
    """The values of (D, X) as the run that decided it wrote them ({cik: values}); {} while none did."""
    got = decided(db, day, auction)
    if got is None:
        return {}
    kind = KIND_OF[(auction, str(got.get("kind")))]
    return {str(r["cik"]): json.loads(r["value"]) for r in db.execute(
        "SELECT cik, value FROM px_features WHERE day=? AND kind=? AND run=?", (day.isoformat(), kind, got["run"]))}


# ----------------------------------------------------------------------------------------------------- the grid
_GRID: list[dict[str, Any]] | None = None


def grid_sha(rows: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(list(rows), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def grid(path: Path | None = None) -> list[dict[str, Any]]:
    """THE PINNED GRID (section 3.3): the 528 records of `px_grid8.json`, REFUSED (ValueError) unless their canonical
    sha256 is `GRID_SHA256`."""
    global _GRID
    if path is None and _GRID is not None:
        return _GRID
    rows = json.loads(Path(path or GRID_FILE).read_text(encoding="utf-8"))
    got = grid_sha(rows)
    if got != GRID_SHA256:
        raise ValueError(f"px_grid8.json's canonical sha256 is {got}, not the pinned {GRID_SHA256}")
    if path is None:
        _GRID = rows
    return rows


#: The value a family's decile is of (section 3.3, the records' value texts).
FAMILY_VALUE = {"REV1": "z1", "REV5": "z5", "REV20": "z20", "REV1S": "z1s", "GAP": "zg", "OPENGAP": "zo", "DAY": "zd",
                "DAYS": "zds", "HI52": "h52", "VOL": "v"}
DRIFT_ID = re.compile(r"PXR-DRIFT-(.+)-K(\d)-(UP|DN)-O1")


def _decile(values: Mapping[str, Mapping[str, Any]], key: str, top: bool,
            keep: Callable[[Mapping[str, Any]], bool] | None = None) -> set[str]:
    """The bottom (top) decile of `key` over the PXU names of the decision with a value: floor(n / 10) names in (value,
    CIK) order (none below 10 names), `keep` filtering after the decile (VOL's z1 sign)."""
    have = [(float(v[key]), cik) for cik, v in values.items() if v.get(key) is not None and math.isfinite(float(v[key]))]
    n = len(have) // 10
    if n == 0:
        return set()
    have.sort(key=lambda x: ((-x[0]) if top else x[0], x[1]))
    chosen = {cik for _, cik in have[:n]}
    return {c for c in chosen if keep is None or keep(values[c])}


def select_record(rec: Mapping[str, Any], values: Mapping[str, Mapping[str, Any]], *,
                  seat_events: Mapping[str, set[str]] | None = None) -> set[str]:
    """THE RECORD GRID EVALUATOR (section 3.3): the CIKs record `rec` selects on D from the values the deciding run of
    its window's auction wrote (`features`): its family's decile over the PXU names of the decision (or DRIFT's, UNIV's
    or SEAT's rule), then its news filter (ANY; NONE: no stored item in the window's span; SOME: one), then its tier
    (ALL; SMALL: benchmark IWM; LARGE: benchmark SPY). `seat_events` (SEAT): {seat id: the CIKs of its shadow events}."""
    fam, side = str(rec["family"]), str(rec["side"])
    if fam in FAMILY_VALUE:
        key = FAMILY_VALUE[fam]
        if fam == "VOL":
            sign = (lambda v: v.get("z1") is not None and float(v["z1"]) > 0) if side == "HIUP" else \
                (lambda v: v.get("z1") is not None and float(v["z1"]) < 0)
            got = _decile(values, key, True, sign)
        else:
            got = _decile(values, key, side == "HI")
    elif fam == "DRIFT":
        m = DRIFT_ID.fullmatch(str(rec["id"]))
        if m is None:
            return set()
        dkey = f"EVL-CTRL-{m.group(1)}|{int(m.group(2))}"
        up = m.group(3) == "UP"
        got = {cik for cik, v in values.items() for z in [(v.get("drift") or {}).get(dkey)]
               if z is not None and (z >= 1.0 if up else z <= -1.0)}
    elif fam == "UNIV":
        got = set(values)
    elif fam == "SEAT":
        got = set((seat_events or {}).get(f"PX-{side}-{rec['window']}", set()))
    else:
        return set()
    news = str(rec["news"])
    if news == "NONE":
        got = {c for c in got if not values[c].get("news")}
    elif news == "SOME":
        got = {c for c in got if values[c].get("news")}
    tier = str(rec["tier"])
    if tier == "SMALL":
        got = {c for c in got if str(values[c].get("bench")) == "IWM"}
    elif tier == "LARGE":
        got = {c for c in got if str(values[c].get("bench")) == "SPY"}
    return got


def records(window: str) -> list[dict[str, Any]]:
    return [r for r in grid() if r["window"] == window]


def window_auction(window: str) -> str:
    return "o1" if window == "O1" else "on"


def seat_events(store: Any, day: dt.date) -> dict[str, set[str]]:
    """{seat id: the CIKs of its shadow events of D} (intents not skipped), for the SEAT records."""
    out: dict[str, set[str]] = {}
    for pid in ("PX-DROP-ON", "PX-SURGE-ON", "PX-GAP-O1"):
        out[pid] = {str(r["cik"]) for r in store.db.execute(
            "SELECT cik FROM intents WHERE program=? AND version=1 AND entry_day=? AND status NOT LIKE 'skipped%'",
            (pid, day.isoformat()))}
    return out


# ----------------------------------------------------------------------------------------------------- the panel
def _bar(px: Any, symbol: str, day: dt.date, adj: str) -> dict[str, Any] | None:
    row = px.db.execute("SELECT * FROM px_bars WHERE symbol=? AND day=? AND adj=?",
                        (symbol.upper(), day.isoformat(), adj)).fetchone()
    return None if row is None else dict(row)


def _adj_px(px: Any, symbol: str, day: dt.date, field: str) -> float | None:
    """A raw daily bar's `field` (o or c) on the adjustment=all basis (the day's adjusted over raw close: splits inside a
    hold through the adjusted ratio, as league/events/score.py `_ratio`)."""
    raw, adj = _bar(px, symbol, day, "raw"), _bar(px, symbol, day, "all")
    v = _pos((raw or {}).get(field))
    rc, ac = _pos((raw or {}).get("c")), _pos((adj or {}).get("c"))
    if v is None or rc is None or ac is None:
        return None
    return v * ac / rc


def panel_row(px: Any, store: Any, day: dt.date, window: str, a: Mapping[str, Any]) -> dict[str, Any] | None:
    """ONE PANEL ROW on the BAR BASIS (section 3.3): the SIP daily bar's open or close at the window's two ends (O1: D's
    open to D's close; ON: D's close to D+1's open; C1: D's close to D+1's close), the benchmark's same bars,
    PREREG-EVL-1 section 5's cost allowance at the name's ADV20 (league/events/score.py `cost_bp`, the equity at P's
    close), r, b and a; None while a bar is missing."""
    from . import score as SC

    nxt = C.nth(store, day, 2)
    if window != "O1" and nxt is None:
        return None
    ends = {"O1": ((day, "o"), (day, "c")), "ON": ((day, "c"), (nxt.day if nxt else day, "o")),
            "C1": ((day, "c"), (nxt.day if nxt else day, "c"))}[window]
    sym, bench = str(a["symbol"]), str(a.get("bench") or "")
    e_in, e_out = _adj_px(px, sym, *ends[0]), _adj_px(px, sym, *ends[1])
    b_in, b_out = _adj_px(px, bench, *ends[0]), _adj_px(px, bench, *ends[1])
    if None in (e_in, e_out, b_in, b_out):
        return None
    prev = C.previous(store, day, 1)
    equity = SC.equity_on(store, prev[0].day) if prev else None
    adv = float(a.get("adv20") or 0)
    c_in, c_out = SC.cost_bp(adv, equity, "entry"), SC.cost_bp(adv, equity, "exit")
    r = SC.after_cost_return(e_in, e_out, c_in, c_out)
    b = b_out / b_in - 1.0
    return {"symbol": sym, "entry_px": e_in, "exit_px": e_out, "bench": bench, "bench_entry": b_in, "bench_exit": b_out,
            "cost_entry_bp": c_in, "cost_exit_bp": c_out, "r": r, "b": b, "a": r - b}


def exit_day(store: Any, day: dt.date, window: str) -> dt.date | None:
    """The session a window of D ends in (O1: D; ON and C1: the session after D)."""
    if window == "O1":
        return day
    nxt = C.nth(store, day, 2)
    return None if nxt is None else nxt.day


def settle_panel(px: Any, store: Any, day: dt.date, *, now: dt.datetime) -> dict[str, Any]:
    """THE NIGHT'S PANEL OF D (section 3.3): each window of D whose exit session's nightly bars are stored (px_meta
    `px:bars:<exit>`, league/events/pxdata.py `daily`), once: one row a PXU(D) name with both bars (`px_panel`,
    WRITE-ONCE; a name with a bar missing has none), then each record's day of that window (`record_days`), then
    `px_basis` for every seat and control event settled on both bases. Counts only."""
    if not registered():
        return {}
    ensure(px)
    am = pxu(px.db, day)
    if not am:
        return {"pxu": 0}
    stamp = S.iso(now)
    out: dict[str, Any] = {"pxu": len(am), "panel": 0, "record_days": 0}
    for window in ("O1", "ON", "C1"):
        key = PANEL_KEY.format(day=f"{day.isoformat()}:{window}")
        if _meta(px.db, key) is not None:
            continue
        end = exit_day(store, day, window)
        if end is None or _meta(px.db, f"px:bars:{end.isoformat()}") is None:
            continue
        with px.tx() as db:
            for cik, a in am.items():
                got = panel_row(px, store, day, window, a)
                if got is None:
                    continue
                cur = db.execute("INSERT OR IGNORE INTO px_panel(day, window, cik, symbol, entry_px, exit_px, bench, "
                                 "bench_entry, bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, status, settled_at) "
                                 "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'settled', ?)",
                                 (day.isoformat(), window, cik, got["symbol"], got["entry_px"], got["exit_px"], got["bench"],
                                  got["bench_entry"], got["bench_exit"], got["cost_entry_bp"], got["cost_exit_bp"],
                                  got["r"], got["b"], got["a"], stamp))
                out["panel"] += cur.rowcount
        out["record_days"] += record_days(px, store, day, window, now=now)
        _set_once(px.db, key, {"at": stamp})
    out["basis"] = write_basis(px, store, now=now)
    return out


def record_days(px: Any, store: Any, day: dt.date, window: str, *, now: dt.datetime) -> int:
    """`px_record_days` of (D, window) (section 3.3): each record of the window, from the values of the run that decided
    its auction (`features`) and the window's settled panel rows of the names it selects, written once (none while no
    run decided the auction)."""
    values = features(px.db, day, window_auction(window))
    if not values:
        return 0
    seats_of = seat_events(store, day)
    panel = {str(r["cik"]): dict(r) for r in px.db.execute("SELECT * FROM px_panel WHERE day=? AND window=?",
                                                           (day.isoformat(), window))}
    written = 0
    with px.tx() as db:
        for rec in records(window):
            chosen = select_record(rec, values, seat_events=seats_of)
            rs = [panel[c] for c in sorted(chosen) if c in panel]
            a = [float(r["a"]) for r in rs]
            cur = db.execute("INSERT OR IGNORE INTO px_record_days(record, day, n, sum_a, sum_a2, sum_r, written_at) "
                             "VALUES(?, ?, ?, ?, ?, ?, ?)",
                             (rec["id"], day.isoformat(), len(rs), math.fsum(a), math.fsum(x * x for x in a),
                              math.fsum(float(r["r"]) for r in rs), S.iso(now)))
            written += cur.rowcount
    return written


def write_basis(px: Any, store: Any, *, now: dt.datetime) -> int:
    """`px_basis` (section 3.3, THE BASIS): for every seat and control event settled on the print basis (the lane's
    `outcomes`) whose bar-basis panel row exists, the bar-basis return beside the print-basis one and the two ends'
    gaps in bp. Measured forward, never a judge input. Written once."""
    written = 0
    window_of = {"PX-DROP-ON": "ON", "PX-SURGE-ON": "ON", "CTRL-PX-ALL-ON": "ON", "PX-GAP-O1": "O1",
                 "CTRL-PX-ALL-O1": "O1"}
    with px.tx() as db:
        for pid, window in window_of.items():
            for o in store.db.execute("SELECT o.*, i.cik, i.entry_day FROM outcomes o JOIN intents i ON i.program=o.program "
                                      "AND i.version=o.version AND i.event=o.event WHERE o.program=? AND o.status='settled'",
                                      (pid,)):
                if db.execute("SELECT 1 FROM px_basis WHERE program=? AND version=? AND event=?",
                              (pid, int(o["version"]), str(o["event"]))).fetchone():
                    continue
                bar = db.execute("SELECT * FROM px_panel WHERE day=? AND window=? AND cik=?",
                                 (str(o["entry_day"]), window, str(o["cik"]))).fetchone()
                if bar is None:
                    continue

                def gap(p: Any, q: Any) -> float | None:
                    return None if not p or not q else (float(p) / float(q) - 1.0) * 1e4
                cur = db.execute("INSERT OR IGNORE INTO px_basis(program, version, event, bar_r, print_r, bar_a, print_a, "
                                 "entry_gap_bp, exit_gap_bp, written_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (pid, int(o["version"]), str(o["event"]), bar["r"], o["r"], bar["a"], o["a"],
                                  gap(o["entry_px"], bar["entry_px"]), gap(o["exit_px"], bar["exit_px"]), S.iso(now)))
                written += cur.rowcount
    return written


# ----------------------------------------------------------------------------------------------------- the placebos
def placebo_ids(window: str) -> list[str]:
    return [f"PLC-PX-{window}-{j}" for j in range(1, PLACEBOS + 1)]


#: The intents of a control that are no event of it (section 3.2-3.4): an issuer A72's rule skips at the decision, and
#: one the hourly re-decision removed (an item knowable in the span, stored after the decision). Every other intent of
#: the control is one of its events, settled or not (a settlement's own skip, at the limit or with no print, keeps it).
NOT_EVENTS = ("skipped:issuer-held", WHY_REMOVED)


def placebo_rows(store: Any, window: str, j: int, *, judged: set[str] | None = None) -> list[dict[str, Any]]:
    """PLACEBO j's record (section 3.3): for each entry session D, THE 8 EVENTS OF ITS WINDOW'S CONTROL ON D
    (CTRL-PX-ALL-ON for ON, CTRL-PX-ALL-O1 for O1) WITH THE SMALLEST sha256("PX-PLACEBO|<window>|<j>|<D>|<cik>"), among
    every event of the control on D (`NOT_EVENTS` aside), then those of them with a settled outcome (a subset of the
    control's settled outcomes: no new intent). An event of the eight that never settles leaves its slot empty that
    session; the ninth never takes it. `judged`: the sessions a live run decided (the record counts no catch-up's)."""
    ctl = "CTRL-PX-ALL-ON" if window == "ON" else "CTRL-PX-ALL-O1"
    from . import screen as SN

    settled = {str(r["event"]): r for r in SN.settled_rows(store, ctl, 1)}
    by_day: dict[str, list[tuple[str, str]]] = {}
    for r in store.db.execute("SELECT entry_day, cik, symbol, event, status FROM intents WHERE program=? AND version=1",
                              (ctl,)):
        if str(r["status"]) in NOT_EVENTS:
            continue
        day = str(r["entry_day"])
        if judged is not None and day not in judged:
            continue
        by_day.setdefault(day, []).append((str(r["cik"] or r["symbol"]), str(r["event"])))
    out = []
    for day, evs in sorted(by_day.items()):
        d = dt.date.fromisoformat(day)
        evs.sort(key=lambda x: placebo_hash(window, j, d, x[0]))
        out += [settled[e] for _, e in evs[:PLACEBO_EVENTS] if e in settled]
    return out


# ----------------------------------------------------------------------------------------------------- the report
def _utc_day(day: dt.date) -> tuple[str, str]:
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=C.NY)
    return S.iso(start), S.iso(start + dt.timedelta(days=1))


def pivot_count(store: Any) -> int:
    """Section 9's count: the settled real-money PX events AT PROBE SIZE OR ABOVE (the buy's band probe or sized, its
    sale filled) of the three seats, from PX's first fill; learning events are never counted."""
    n = 0
    for pid in ("PX-DROP-ON", "PX-SURGE-ON", "PX-GAP-O1"):
        for r in store.db.execute("SELECT b.event FROM real_fills b JOIN real_fills s ON s.program=b.program AND "
                                  "s.version=b.version AND s.event=b.event AND s.side='sell' WHERE b.program=? AND "
                                  "b.side='buy' AND b.band IN ('probe', 'sized')", (pid,)):
            n += 1
    return n


def report_lines(store: Any, root: Any, day: dt.date) -> dict[str, Any]:
    """THE REPORT'S PX BLOCK of D (section 10), COUNTS ONLY: N_U, the FLAGGED share, the share with premarket bars, the
    panel rows written and settled, each seat's qualifying names, shadow K, the controls' counts, the parts cut, not
    started or decided by catch-up, and the audit's state (how many placebos have passed: a count). No record's,
    placebo's, panel's or sub-rule's figure. {} while this file registers nothing."""
    if not registered():
        return {}
    db = read_only(root)
    if db is None:
        return {"px": "no px.sqlite"}
    try:
        out: dict[str, Any] = {"day": day.isoformat()}
        try:
            am = db.execute("SELECT COUNT(*) AS n, SUM(in_pxu) AS u, SUM(CASE WHEN why LIKE 'flagged%' THEN 1 ELSE 0 END) "
                            "AS f FROM px_am WHERE day=?", (day.isoformat(),)).fetchone()
        except sqlite3.Error:
            return {"px": "no PX tables yet"}
        n = int(am["n"] or 0)
        out["N_U"] = int(am["u"] or 0)
        out["flagged_share"] = round(int(am["f"] or 0) / n, 4) if n else None
        o1 = features(db, day, "o1")
        pop = [v for v in o1.values() if v.get("gap_pop")]
        out["premarket_share"] = round(sum(1 for v in pop if v.get("pm") is not None) / len(pop), 4) if pop else None
        out["panel_rows"] = int(db.execute("SELECT COUNT(*) FROM px_panel WHERE day=?", (day.isoformat(),)).fetchone()[0])
        for auction in AUCTIONS:
            got = decided(db, day, auction)
            out[f"decided_{auction}"] = None if got is None else got.get("kind")
        am_done = _meta_json(db, AM_KEY.format(day=day.isoformat()))
        # (section 4.6: PXU(D) stored before 09:15 serves both auctions, in [09:15, 15:30) only the ON one, none: neither)
        out["auctions_lost_am"] = 2 if am_done is None else (1 if am_done.get("serves") == "on" else 0)
        progs: dict[str, Any] = {}
        for p in P.rows_8():
            if not p.px:
                continue
            rows = store.db.execute("SELECT status, COUNT(*) AS n FROM intents WHERE program=? AND version=? AND entry_day=? "
                                    "GROUP BY status", (p.id, p.version, day.isoformat())).fetchall()
            progs[p.id] = {str(r["status"]): int(r["n"]) for r in rows}
        out["programs"] = progs
        runs = db.execute("SELECT status, COUNT(*) AS n, SUM(requests) AS r FROM px_runs WHERE started_at>=? AND "
                          "started_at<? GROUP BY status", _utc_day(day)).fetchall()
        out["runs"] = {str(r["status"]): int(r["n"]) for r in runs}
        out["requests"] = int(sum(int(r["r"] or 0) for r in runs))
        out["plan_minutes"] = round(out["requests"] / 200.0, 2)
        gaps: dict[str, list[float]] = {"entry": [], "exit": []}
        for r in db.execute("SELECT entry_gap_bp, exit_gap_bp FROM px_basis"):
            for side in ("entry", "exit"):
                if r[f"{side}_gap_bp"] is not None:
                    gaps[side].append(abs(float(r[f"{side}_gap_bp"])))
        out["basis_bp"] = {side: None if not xs else {"n": len(xs), "mean": round(math.fsum(xs) / len(xs), 2),
                                                       "p90": round(sorted(xs)[max(0, math.ceil(0.9 * len(xs)) - 1)], 2)}
                           for side, xs in gaps.items()}
        out["pivot_count"] = pivot_count(store)
        passed = db.execute("SELECT COUNT(DISTINCT placebo) FROM px_placebo WHERE passed=1 AND placebo LIKE 'PLC-%'"
                            ).fetchone()[0]
        out["placebos_passed"] = int(passed or 0)
        canary = db.execute("SELECT COUNT(DISTINCT placebo) FROM px_placebo WHERE passed=1 AND placebo LIKE 'CTRL-%'"
                            ).fetchone()[0]
        out["canary"] = int(canary or 0)
        return out
    finally:
        db.close()


__all__ = ["K", "CONTROL_N", "Z_SEAT", "DROP_MOVE", "SURGE_MOVE", "SURGE_VOLUME", "GAP_MOVE", "GAP_MIN_ADV",
           "FLAG_TOLERANCE", "SIGMA_SESSIONS", "HIGH_SESSIONS", "VOLUME_SESSIONS", "GROUP_MIN", "PLACEBOS",
           "PLACEBO_EVENTS", "PLACEBO_ALARM", "GRID_SHA256", "GRID_FILE", "DRIFT_CONTROLS", "DRIFT_KS", "AUCTIONS",
           "WINDOWS_OF", "KIND_OF", "DECIDED_KEY", "AM_KEY", "MID_KEY", "PANEL_KEY", "JOB_LIVE", "JOB_CATCHUP", "JOB_AM",
           "JOB_MID", "RELEASE_KEY", "RAN_KEY", "AT_OF", "CLOSE_READS_UNTIL", "READ_CAP", "live_run", "live_features",
           "live_selections", "live_marks", "WHY_LIVE", "WHY_CATCHUP", "WHY_REMOVED", "AM_AT", "AM_BUDGET", "AM_UNTIL", "MID_AT",
           "OPEN_BOUND", "OPEN_UNTIL", "CLOSE_LAST_REQUEST", "CLOSE_DONE", "SCHEMA_8", "TABLES_8", "FEATURE_COLUMNS",
           "PxCutShort", "CODE_SHA", "release_id", "code_identity", "registered", "program", "seats", "control", "auction_of", "event_id", "parse_event", "knowable",
           "event_knowable", "tau", "spans", "ensure", "open_px", "read_only", "decided", "release_at", "mark_release",
           "live_allowed", "item_ciks", "reread", "drift_events", "morning", "pxu", "mid", "read_minutes", "values_on",
           "values_o1", "qualifies", "ranked", "control_population", "control_hash", "placebo_hash", "take", "write_rows",
           "decide", "redecide", "live_picks", "universe_row", "judged_days", "features", "grid_sha", "grid",
           "FAMILY_VALUE", "select_record", "records", "window_auction", "seat_events", "panel_row", "exit_day",
           "settle_panel",
           "record_days", "write_basis", "NOT_EVENTS", "placebo_ids", "placebo_rows", "pivot_count", "report_lines"]
