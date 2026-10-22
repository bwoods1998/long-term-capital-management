"""The pre-registered programs of PREREG-EVL-1 section 6 and PREREG-EVL-2 section 3, and the shadow decisions that
apply them.

Nothing here may change for a registered program: a change is a new version with its own registration time. The
registration time is the commit time of docs/prereg/PREREG-EVL-1.md on `prereg/evl-1` (pinned below once committed);
an event counts only when its knowable time is after it.

Decision windows (league.events.calendar):
- OPEN entry on session D takes exactly the events knowable in [P 09:00 ET, D 09:00 ET), P the session before D
  (these are the events whose "first session whose 09:00 ET is after the knowable time" is D).
- C1's day 0 is D for exactly the events knowable in [P's close decision, D's close decision).
- NEWS-READ on D takes single-symbol articles created after P's 16:00 ET and before D's 09:00 ET.
- PREREG-EVL-2's day-news programs on D take single-symbol articles knowable after D's 09:00 ET and at or before T29
  (15:29 ET on a full day); they enter at D's close and exit at the next session's open.
- PREREG-EVL-4's programs on D (all enter at D's close and exit at the next session's open) take, from issuers not
  EXCLUDED on D (an issuer with an item 2.02 8-K in D's close window, ERN(D), or an article of D's day-news window,
  DAY(D), whatever their knowable times relative to any registration time): F8K(D), the 8-Ks of D's close window with
  EVL-8K-READ-O1's items (1.01, 2.01, 7.01, 8.01, no 2.02), and PM(D), the articles of EVL-NEWS-READ-O1's window of D
  (EVL-NEWSPM-READ-ON skips an issuer with any F8K(D) filing). The sets that skip are read with no registration floor
  (`filings_window`, `news_rows`, `close_rows_4`); the events are each program's own, knowable after ITS registration.
- PREREG-EVL-5's programs on D (all enter at D's close and exit at the next session's open; section 1.1), P the session
  before D and P' the one before P: EVL-ERN-DROP-ON and EVL-ERN-UNDER-ON (and UNDER's control) take ERN(D)'s filings (the
  item 2.02 8-Ks of D's close window) of eligible issuers not TAKEN AT D'S CLOSE BY AN EARLIER ROW (an ERN(D) reaction
  >= 1.04, a DAY(D) article scoring >= 2 or a day-news reaction >= 1.04: `taken_close_5`), UNDER also skipping an issuer
  with an ERN(D) reaction <= 0.96 (`dropped_ciks`); EVL-NEWS-NIGHT2-ON takes the attention articles of P (single-symbol
  articles knowable after P''s close and by T29 of P, `attention_window`) of eligible issuers with NO NEW INFORMATION on
  D (`no_new_info`: no article naming the issuer after T29 of P, no 8-K from P''s close decision, no insider buy from
  09:00 ET of P, each through D's close decision), ranked by the gap at D's 09:30 minute bar. Every set that skips is
  read with no registration floor (`filings_window`, `news_rows`, `news_named`, `ins_buys_window`).
Eligibility (league.events.universe) is decided before any verdict is asked, so verdicts are paid only for eligible
issuers; controls take every eligible event of their program's family, any verdict.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import calendar as C
from . import store as S

#: The registration time (UTC): the prereg's commit time on `prereg/evl-1`. None refuses every decision.
REGISTERED_AT: str | None = "2026-10-19T01:08:38Z"  # A61: tag prereg-evl-1, commit 3d6194dd
#: PREREG-EVL-2's registration time (its second wave counts only events knowable after it).
REGISTERED_AT_2: str = "2026-10-19T03:04:07Z"  # A63: tag prereg-evl-2, commit 93cd4877
#: PREREG-EVL-3's registration time: version 2 of the nine seatable programs, real money at learning size from birth.
REGISTERED_AT_3: str = "2026-10-19T05:23:06Z"  # A64: tag prereg-evl-3, commit 6d3fa8d1
#: PREREG-EVL-4's registration time (births by the captain): three new seatable programs, VERSION 1 their seating
#: version, at PREREG-EVL-3's learning band from birth, and two controls. Its programs count only events knowable after
#: THIS time (not PREREG-EVL-1's, -2's or -3's). None refuses every decision of its programs.
REGISTERED_AT_4: str | None = "2026-10-19T16:01:05Z"  # A71: tag prereg-evl-4, commit cef9810a
#: PREREG-EVL-5's registration time (births by the captain, A92: the latest of its commit's time 21:26:18Z, GitHub's
#: activity time for the branch push 21:26:19Z and the pushing client's clock after the tag push returned 21:26:21Z):
#: three new seatable programs, VERSION 1 their seating version, at PREREG-EVL-3's learning band from birth, and one
#: control. Its programs count only events knowable after THIS time (not PREREG-EVL-1's, -2's, -3's or -4's). None
#: refuses every decision of its programs.
REGISTERED_AT_5: str | None = "2026-10-21T21:26:21Z"  # A92: tag prereg-evl-5, commit b73f205f
#: The files whose seatable rows may trade real money: PREREG-EVL-3 (version 2 of the nine seatable programs of
#: PREREG-EVL-1 and -2), PREREG-EVL-4 (version 1 of its three: its ids are new, so their version 1 is registered
#: with PREREG-EVL-3's bands, section 2) and PREREG-EVL-5 (version 1 of its three, as PREREG-EVL-4's: its section 2).
#: Version 1 of PREREG-EVL-1's and -2's ids, records and controls never seat.
SEATING_PREREGS = (3, 4, 5)

ERN_ITEMS = frozenset({"2.02"})
OTHER_ITEMS = frozenset({"1.01", "2.01", "7.01", "8.01"})
READ_MIN_SCORE = 2
REACT_RATIO = 1.04
INS_WINDOW = dt.timedelta(days=10)
INS_MIN_OWNERS = 2
INS_MIN_VALUE = 50_000.0
ISSUER_GAP_SESSIONS = 5
NEWS_UPDATE_LIMIT = dt.timedelta(minutes=10)
GUIDE_MIN_SCORE = 1          # PREREG-EVL-2: guidance "raised" and score >= 1
TOP_SCORE = 3                # PREREG-EVL-2's READ3 record: score exactly 3
INS_BUY_MIN_VALUE = 50_000.0  # PREREG-EVL-2: one Form 4's director/officer open-market buys
T29_BEFORE_CLOSE = dt.timedelta(minutes=31)  # PREREG-EVL-2's T29: 15:29 ET on a full day
DROP_RATIO = 0.96            # PREREG-EVL-5: EVL-ERN-DROP-ON's reaction <= 0.96; EVL-ERN-UNDER-ON's above it
GAP_RATIO = 1.02             # PREREG-EVL-5: EVL-NEWS-NIGHT2-ON's gap >= 1.02 (D's 09:30 minute's open over P's close)
GUIDE_BONUS = 0.5            # PREREG-EVL-5: EVL-ERN-UNDER-ON's ranking, the score plus 0.5 when guidance is "raised"


@dataclasses.dataclass(frozen=True)
class Program:
    id: str
    version: int
    seatable: bool
    family: str          # ern | ern-react | 8k | ins | news | ins-buy | news-day | news-react | 8k-react | 8k-day | news-pm
    #                      | ern-drop | ern-under | news-night2 (PREREG-EVL-5)
    entry_at: str        # open | close
    hold: int            # sessions held (block length); C1 enters at day 0's close and exits at the next close
    reads: bool          # needs a verdict (its rule below reads the score)
    exit_at: str = "close"   # PREREG-EVL-2's overnight programs exit at the next session's OPEN
    rule: str = "min2"       # min2 (score >= 2) | guide | top (score 3) | none; ern-react adds the reaction
    prereg: int = 1          # which pre-registration (and so which registration time) the program belongs to
    #: R3 (league/events/births.py): a REGISTERED BIRTH's own registration time (the later of GitHub's commit time of its
    #: line in docs/births/ and the House's receipt of that answer) and its canonical spec (JSON: its rule, which
    #: `select` hands to births.select). None for every PREREG program, whose rule and time are the ones above.
    born_at: str | None = None
    spec: str | None = None

    @property
    def key(self) -> tuple[str, int]:
        return (self.id, self.version)

    @property
    def born(self) -> bool:
        """A registered birth of R3 (its rule is its spec's, its time its own registration's)."""
        return self.spec is not None

    @property
    def registered_at(self) -> dt.datetime:
        """The program's OWN registration time, its file's (an event counts only when knowable after it): PREREG-EVL-1's,
        -2's, -3's, -4's or -5's; never another file's (PREREG-EVL-4: "not PREREG-EVL-1's, -2's or -3's"; PREREG-EVL-5:
        "not PREREG-EVL-1's, -2's, -3's or -4's"). A file this code
        does not know has none (ValueError), so no event of it is ever counted under another file's time. A registered
        birth (R3) has its OWN registration time (`born_at`), never its file's."""
        if self.born_at is not None:
            return S.parse_iso(self.born_at)
        if self.prereg == 1:
            return registered()
        if self.prereg == 2:
            return S.parse_iso(REGISTERED_AT_2)
        if self.prereg == 3:
            return S.parse_iso(REGISTERED_AT_3)
        if self.prereg == 4:
            if REGISTERED_AT_4 is None:
                raise RuntimeError("PREREG-EVL-4 is not pinned: none of its programs decides before its registration time")
            return S.parse_iso(REGISTERED_AT_4)
        if self.prereg == 5:
            if REGISTERED_AT_5 is None:
                raise RuntimeError("PREREG-EVL-5 is not pinned: none of its programs decides before its registration time")
            return S.parse_iso(REGISTERED_AT_5)
        raise ValueError(f"no registration time is pinned for PREREG-EVL-{self.prereg}")

    @property
    def can_seat(self) -> bool:
        """Whether this version may ever trade real money: PREREG-EVL-3 section 1, version 2 of the nine seatable
        programs (prereg 3), PREREG-EVL-4 section 2, version 1 of its three seatable programs (prereg 4: its seating
        version), and PREREG-EVL-5 section 2, version 1 of its three (prereg 5, the same). Version 1 of PREREG-EVL-1's and -2's programs stays a shadow record with its own screen, never seated;
        a record or a control (`seatable` False) never seats, whatever its file. R3: a seatable registered birth (prereg
        3: PREREG-EVL-3's learning band, screen and limit at entry) seats at its own version 1 (R3-SPEC section 1)."""
        return self.seatable and self.prereg in SEATING_PREREGS


PROGRAMS = (
    Program("EVL-ERN-READ-O1", 1, True, "ern", "open", 1, True),
    Program("EVL-ERN-READ-O3", 1, False, "ern", "open", 3, True),        # a record (overlapping holds)
    Program("EVL-ERN-REACT-C1", 1, True, "ern-react", "close", 1, False),
    Program("EVL-8K-READ-O1", 1, True, "8k", "open", 1, True),
    Program("EVL-INS-CLUSTER-O5", 1, False, "ins", "open", 5, False),    # a record (too few events)
    Program("EVL-NEWS-READ-O1", 1, True, "news", "open", 1, True),
    Program("EVL-CTRL-ERN-ALL-O1", 1, False, "ern", "open", 1, False),
    Program("EVL-CTRL-8K-ALL-O1", 1, False, "8k", "open", 1, False),
    Program("EVL-CTRL-NEWS-ALL-O1", 1, False, "news", "open", 1, False),
    # PREREG-EVL-2 (registered 2026-10-19T03:04:07Z): five seatable programs, three records, one control.
    Program("EVL-ERN-REACT-ON", 1, True, "ern-react", "close", 1, False, exit_at="open", rule="none", prereg=2),
    Program("EVL-ERN-GUIDE-O1", 1, True, "ern", "open", 1, True, rule="guide", prereg=2),
    Program("EVL-INS-BUY-O1", 1, True, "ins-buy", "open", 1, False, rule="none", prereg=2),
    Program("EVL-NEWS-READ-ON", 1, True, "news-day", "close", 1, True, exit_at="open", prereg=2),
    Program("EVL-NEWS-REACT-ON", 1, True, "news-react", "close", 1, False, exit_at="open", rule="none", prereg=2),
    Program("EVL-INS-BUY-O5", 1, False, "ins-buy", "open", 5, False, rule="none", prereg=2),      # a record
    Program("EVL-ERN-REACT-READ-C1", 1, False, "ern-react", "close", 1, True, prereg=2),           # a record
    Program("EVL-ERN-READ3-O1", 1, False, "ern", "open", 1, True, rule="top", prereg=2),           # a record
    Program("EVL-CTRL-NEWS-DAY-ON", 1, False, "news-day", "close", 1, False, exit_at="open", rule="none", prereg=2),
)
#: PREREG-EVL-3 (registered 2026-10-19T05:23:06Z): version 2 of every seatable program, the same events and rules as
#: its version 1 (PREREG-EVL-2's limit at entry for all nine: prereg >= 2), real money at learning size from birth.
PROGRAMS = PROGRAMS + tuple(dataclasses.replace(p, version=2, prereg=3) for p in PROGRAMS if p.seatable)
#: PREREG-EVL-4 (registered 2026-10-19T16:01:05Z; births by the captain): three seatable programs at PREREG-EVL-3's
#: learning band from birth, VERSION 1 their seating version (section 2), in section 1.2's order (ROOM's order within a
#: band follows it, after every row of PREREG-EVL-1 and -2), and two controls (section 4: free records that never seat).
#: Each enters at the CLOSE of D and exits at the OPEN of the next session (hold 1), with PREREG-EVL-2's limit at entry
#: (score.py: prereg >= 2). Appended AFTER PREREG-EVL-3's version 2 copies, so no version 2 of these ids exists.
PROGRAMS = PROGRAMS + (
    Program("EVL-8K-REACT-ON", 1, True, "8k-react", "close", 1, False, exit_at="open", rule="none", prereg=4),
    Program("EVL-8K-READ-ON", 1, True, "8k-day", "close", 1, True, exit_at="open", prereg=4),
    Program("EVL-NEWSPM-READ-ON", 1, True, "news-pm", "close", 1, True, exit_at="open", prereg=4),
    Program("EVL-CTRL-8K-ON", 1, False, "8k-day", "close", 1, False, exit_at="open", rule="none", prereg=4),
    Program("EVL-CTRL-NEWSPM-ON", 1, False, "news-pm", "close", 1, False, exit_at="open", rule="none", prereg=4),
)
#: PREREG-EVL-5 (registered 2026-10-21T21:26:21Z; births by the captain, A92): three seatable programs at PREREG-EVL-3's
#: learning band from birth, VERSION 1 their seating version (section 2), in section 1.2's order (ROOM's order within a
#: band follows it, after every row of PREREG-EVL-1, -2 and -4; R3's births after them), and one control (section 4: a
#: free record that never seats). Each enters at the CLOSE of D and exits at the OPEN of the next session (hold 1), with
#: PREREG-EVL-2's limit at entry (score.py: prereg >= 2). Appended AFTER PREREG-EVL-4's rows.
PROGRAMS = PROGRAMS + (
    Program("EVL-ERN-DROP-ON", 1, True, "ern-drop", "close", 1, False, exit_at="open", rule="none", prereg=5),
    Program("EVL-ERN-UNDER-ON", 1, True, "ern-under", "close", 1, True, exit_at="open", prereg=5),
    Program("EVL-NEWS-NIGHT2-ON", 1, True, "news-night2", "close", 1, False, exit_at="open", rule="none", prereg=5),
    Program("EVL-CTRL-ERN-UNDER-ON", 1, False, "ern-under", "close", 1, False, exit_at="open", rule="none", prereg=5),
)
#: Every program version by (id, version).
BY_KEY = {(p.id, p.version): p for p in PROGRAMS}
#: Version 1 of every program by id (the records and controls exist at version 1 only).
BY_ID = {p.id: p for p in PROGRAMS if p.version == 1}
#: The versions that may ever trade real money (PREREG-EVL-3 section 1, PREREG-EVL-4 and -5 section 2), in the tables'
#: order: the nine version 2 rows (PREREG-EVL-1's four, then PREREG-EVL-2's five), then PREREG-EVL-4's three, then
#: PREREG-EVL-5's three (version 1).
SEATING = tuple(p for p in PROGRAMS if p.can_seat)
#: THE PREREG PROGRAMS (PREREG-EVL-1 to -5), fixed: `load_births` keeps them first and unchanged, and adds the
#: registered births after them (after PREREG-EVL-5's rows, so ROOM's order puts every PREREG program first).
PREREG_PROGRAMS = PROGRAMS
PREREG_SEATING = SEATING
#: R3's registered births as last loaded from a store (`load_births`), in registration order, each READ birth followed
#: by its derived control (a record).
BIRTHS: tuple[Program, ...] = ()
_LOAD = threading.Lock()
#: (the store's root, the births) of the last load that READ its store's `births` table (`load_births`): what a later
#: load of the SAME store keeps when its read fails (release 1019e's review).
_LAST_READ: tuple[str | None, tuple[Program, ...]] = (None, ())


def _where(store: Any) -> str | None:
    """The store's root, resolved (the lane's `Store` and the book's read-only `Lane` of one store give the same), or
    None when it has none."""
    root = getattr(store, "root", None)
    if root is None:
        return None
    try:
        return str(Path(root).resolve())
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def registered() -> dt.datetime:
    if REGISTERED_AT is None:
        raise RuntimeError("PREREG-EVL-1 is not pinned: no decision is made before its registration time")
    return S.parse_iso(REGISTERED_AT)


def load_births(store: Any) -> tuple[Program, ...]:
    """R3'S ONE LOADER (goal-2026-10-19/R3-SPEC.md; league/events/births.py): every birth registered in `store`'s
    `births` table (filled only from the gateway's receipts of its docs/births/ line), in registration order, as a
    Program row with its own registration time, PREREG-EVL-3's learning band, screen and minimums (prereg 3) and its
    spec's rule; a READ birth followed by its derived control (a record). They are added AFTER every PREREG program:
    PROGRAMS, BY_KEY, BY_ID and SEATING are rebound with the PREREG rows first and unchanged (no PREREG program's
    selection, judge or constant moves), so the lane's decisions, its screen (`screen.expected_false_passes` counts each
    seatable birth's 0.10 through SEATING), its bands and the House's event book (league/events/book.py, which reads
    SEATING and BY_KEY) take them like any version 2 program. `store` is the lane's store or the book's read-only view
    of it (`.db`); a store without the table loads none (and a load that would give two rows one key loads none); None
    unloads every birth. A store whose `births` table CANNOT BE READ keeps the births last read from that same store
    (release 1019e's review: the rows are process-wide and both House threads, the lane's and the book's, load them,
    so a read error that unloaded them would have the next decision made, and the next record settled, as if a
    registered birth did not exist: its events left out of its shadow record and its entries settled with no limit at
    entry); a store never read before loads none (fail closed: nothing seats). Returns the births loaded."""
    global PROGRAMS, BY_KEY, BY_ID, SEATING, BIRTHS, _LAST_READ
    from . import births as BI

    where = None if store is None else _where(store)
    try:
        born = () if store is None else tuple(BI.registered_programs(store))
        read = True
    except Exception:  # noqa: BLE001 - an unreadable births table: the same store's last read births, else none
        last_where, last_born = _LAST_READ
        born = last_born if where is not None and where == last_where else ()
        read = False
    with _LOAD:
        programs = PREREG_PROGRAMS + born
        by_key = {(p.id, p.version): p for p in programs}
        if len(by_key) != len(programs):
            born, programs = (), PREREG_PROGRAMS
            by_key = {(p.id, p.version): p for p in programs}
        if store is None:
            _LAST_READ = (None, ())
        elif read:
            _LAST_READ = (where, born)
        BIRTHS = born
        BY_KEY = by_key
        BY_ID = {p.id: p for p in programs if p.version == 1}
        SEATING = PREREG_SEATING + tuple(p for p in born if p.can_seat)
        PROGRAMS = programs
    return born


# ---------------------------------------------------------------------------------------------------- windows
def open_window(store: S.Store, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    d = C.session(store, day)
    prior = C.previous(store, day, 1)
    if d is None or not prior:
        raise LookupError(f"no session {day} or none before it")
    return prior[0].open_cutoff, d.open_cutoff


def close_window(store: S.Store, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    d = C.session(store, day)
    prior = C.previous(store, day, 1)
    if d is None or not prior:
        raise LookupError(f"no session {day} or none before it")
    return prior[0].close_decide, d.close_decide


def news_window(store: S.Store, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    d = C.session(store, day)
    prior = C.previous(store, day, 1)
    if d is None or not prior:
        raise LookupError(f"no session {day} or none before it")
    return prior[0].close_at, d.open_cutoff  # knowable after P's close and by D's 09:00 ET


def day_news_window(store: S.Store, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """PREREG-EVL-2's day-news window of D: knowable after 09:00 ET of D and at or before T29 of D (the start of the
    regular-session minute bar 31 minutes before the close)."""
    d = C.session(store, day)
    if d is None:
        raise LookupError(f"no session {day}")
    return d.open_cutoff, d.close_at - T29_BEFORE_CLOSE


# ---------------------------------------------------------------------------------------------------- events
def filings_in(store: S.Store, form: str, lo: dt.datetime, hi: dt.datetime, *,
               since: dt.datetime | None = None) -> list[Mapping[str, Any]]:
    """Fetched filings of `form` knowable in [lo, hi) and after the registration time, oldest first. `since` (R3's
    outcome-free facts, league/events/births.py, which count what a rule WOULD have selected in sessions before any
    registration): another time than PREREG-EVL-1's registration; no decision passes it."""
    since = registered() if since is None else since
    lo = max(lo, since)
    rows = store.db.execute("SELECT * FROM filings WHERE form=? AND status='fetched' AND knowable_at>=? AND knowable_at<? "
                            "ORDER BY knowable_at, accession", (form, S.iso(lo), S.iso(hi)))
    return [dict(r) for r in rows if S.parse_iso(r["knowable_at"]) > since]


def items_of(row: Mapping[str, Any]) -> set[str]:
    try:
        return set(json.loads(row.get("items") or "[]"))
    except ValueError:
        return set()


def news_in(store: S.Store, lo: dt.datetime, hi: dt.datetime, *,
            since: dt.datetime | None = None) -> list[Mapping[str, Any]]:
    """Single-symbol articles KNOWABLE in (lo, hi] and after the registration time, oldest first (PREREG draft 2:
    knowable after the previous session's close and by 09:00 ET of D). `since`: as `filings_in`'s."""
    since = registered() if since is None else since
    rows = store.db.execute("SELECT * FROM news WHERE knowable_at>? AND knowable_at<=? ORDER BY knowable_at, id",
                            (S.iso(lo), S.iso(hi)))
    out = []
    for r in rows:
        if S.parse_iso(r["knowable_at"]) <= since:
            continue
        if not r["live"] and r["updated_at"] and \
                S.parse_iso(r["updated_at"]) - S.parse_iso(r["created_at"]) > NEWS_UPDATE_LIMIT:
            continue  # backfilled and edited more than 10 minutes after publication (PREREG section 3)
        try:
            symbols = json.loads(r["symbols"] or "[]")
        except ValueError:
            continue
        if isinstance(symbols, list) and len(symbols) == 1:
            out.append(dict(r) | {"symbol": str(symbols[0]).upper()})
    return out


# ---------------------------------------------------------------------------------------------------- PREREG-EVL-4
#: PREREG-EVL-4's families: its two 8-K rows read F8K(D) (EVL-8K-READ-O1's item rule) and its news rows read PM(D).
FAMILY_8K = ("8k", "8k-react", "8k-day")
CLOSE_FAMILIES_4 = ("8k-react", "8k-day", "news-pm")


def filings_window(store: S.Store, form: str, lo: dt.datetime, hi: dt.datetime) -> list[Mapping[str, Any]]:
    """Fetched filings of `form` knowable in [lo, hi), oldest first, with NO registration floor: PREREG-EVL-4's sets that
    skip an issuer (ERN(D), F8K(D)) carry no registration condition (its section 1.2, the adversarial check's build note
    (i)). The events of a program are still only those knowable after its own registration time (`select`).
    `filings_in`, the earlier files' reader, is unchanged."""
    rows = store.db.execute("SELECT * FROM filings WHERE form=? AND status='fetched' AND knowable_at>=? AND knowable_at<? "
                            "ORDER BY knowable_at, accession", (form, S.iso(lo), S.iso(hi)))
    return [dict(r) for r in rows]


def news_rows(store: S.Store, lo: dt.datetime, hi: dt.datetime) -> list[Mapping[str, Any]]:
    """Single-symbol articles KNOWABLE in (lo, hi], oldest first, PREREG-EVL-1 section 3's non-live exclusion applied,
    each with its one `symbol`, and NO registration floor (PREREG-EVL-4: DAY(D) and PM(D) as the sets that skip carry
    none; `select` keeps as a program's events only those knowable after its own registration time). `news_in`, the
    earlier files' reader, is unchanged."""
    rows = store.db.execute("SELECT * FROM news WHERE knowable_at>? AND knowable_at<=? ORDER BY knowable_at, id",
                            (S.iso(lo), S.iso(hi)))
    out = []
    for r in rows:
        if not r["live"] and r["updated_at"] and \
                S.parse_iso(r["updated_at"]) - S.parse_iso(r["created_at"]) > NEWS_UPDATE_LIMIT:
            continue  # backfilled and edited more than 10 minutes after publication (PREREG-EVL-1 section 3)
        try:
            symbols = json.loads(r["symbols"] or "[]")
        except ValueError:
            continue
        if isinstance(symbols, list) and len(symbols) == 1:
            out.append(dict(r) | {"symbol": str(symbols[0]).upper()})
    return out


def family_8k(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """F8K's item rule (EVL-8K-READ-O1's family, PREREG-EVL-1 section 6): the 8-K rows with any of items 1.01, 2.01, 7.01,
    8.01 and without item 2.02 (the filing's own items, as the lane stores them)."""
    out = []
    for r in rows:
        items = items_of(r)
        if items & OTHER_ITEMS and not items & ERN_ITEMS:
            out.append(r)
    return out


def ern_ciks(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    """ERN(D)'s issuers: the CIKs of the 8-K rows (D's close window) with item 2.02, whatever their verdict or reaction."""
    return {str(r["cik"]) for r in rows if r.get("cik") and items_of(r) & ERN_ITEMS}


def day_ciks(articles: Iterable[Mapping[str, Any]], symbol_of: Callable[[str], str | None]) -> set[str]:
    """DAY(D)'s issuers: those of the day-news window's articles (each carrying its issuer's `cik`) whose one symbol is
    the issuer's ELIGIBLE ticker for D (`symbol_of(cik)`; None when the issuer is not eligible), whatever their verdict or
    reaction."""
    out = set()
    for a in articles:
        cik = a.get("cik")
        if not cik:
            continue
        symbol = symbol_of(str(cik))
        if symbol is not None and symbol == a.get("symbol"):
            out.add(str(cik))
    return out


def f8k_ciks(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    """The issuers with any F8K(D) filing among the 8-K rows of D's close window (EVL-NEWSPM-READ-ON's skip, whatever the
    filing's verdict, reaction or knowable time relative to any registration time)."""
    return {str(r["cik"]) for r in family_8k(rows) if r.get("cik")}


def excluded(ern_rows: Iterable[Mapping[str, Any]], day_articles: Iterable[Mapping[str, Any]],
             symbol_of: Callable[[str], str | None]) -> set[str]:
    """EXCLUDED on D (PREREG-EVL-4 section 1.1): an issuer in ERN(D) (`ern_rows`: the 8-Ks of D's close window, any
    items; those with 2.02 count) or in DAY(D) (`day_articles`, `symbol_of` as `day_ciks`). Every program and control of
    PREREG-EVL-4 skips it, whatever the knowable times of the rows that put it there."""
    return ern_ciks(ern_rows) | day_ciks(day_articles, symbol_of)


def close_rows_4(all8k: Iterable[Mapping[str, Any]], day_articles: Iterable[Mapping[str, Any]],
                 pm_articles: Iterable[Mapping[str, Any]], symbol_of: Callable[[str], str | None]
                 ) -> dict[str, list[Mapping[str, Any]]]:
    """PREREG-EVL-4's rows of entry session D before each program's own rule (section 1.2): {"8k-react", "8k-day": the
    F8K(D) filings of issuers not EXCLUDED on D; "news-pm": the PM(D) articles of issuers not EXCLUDED on D and with no
    F8K(D) filing}. `all8k`: every fetched 8-K of D's close window; `day_articles`: PREREG-EVL-2's day-news window of D;
    `pm_articles`: EVL-NEWS-READ-O1's window of D; every article carrying its issuer's `cik`; all read with NO
    registration floor (`filings_window`, `news_rows`). `symbol_of(cik)`: the issuer's eligible ticker for D, or None.
    The filters here carry no registration condition; `select` takes as a program's events only the rows knowable after
    its own registration time, and applies eligibility (the eligible ticker for an article) and the program's rule."""
    rows8k = list(all8k)
    skip = excluded(rows8k, day_articles, symbol_of)
    fam = family_8k(rows8k)
    filed = {str(r["cik"]) for r in fam if r.get("cik")}
    f8k = [r for r in fam if str(r.get("cik")) not in skip]
    pm = [a for a in pm_articles if a.get("cik") and str(a["cik"]) not in skip and str(a["cik"]) not in filed]
    return {"8k-react": f8k, "8k-day": list(f8k), "news-pm": pm}


# ---------------------------------------------------------------------------------------------------- PREREG-EVL-5
#: PREREG-EVL-5's families (section 1.2): its two earnings rows read ERN(D)'s filings (item 2.02; event `8k:<accession>`)
#: and its news row the attention articles of P (event `news:<id>`). None of them is a REACT family (`REACT_FAMILIES`'
#: >= 1.04 never applies to them): each has its own rule in `select`.
FAMILY_ERN_5 = ("ern-drop", "ern-under")
CLOSE_FAMILIES_5 = ("ern-drop", "ern-under", "news-night2")


def attention_window(store: S.Store, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """THE ATTENTION ARTICLES OF P for entry session D = `day` (PREREG-EVL-5 section 1.1): knowable after the close of P'
    and at or before T29 of P (EVL-NEWS-READ-O1's window of P joined to PREREG-EVL-2's day-news window of P), P the
    session before D and P' the one before P."""
    back = C.previous(store, day, 2)
    if C.session(store, day) is None or len(back) < 2:
        raise LookupError(f"no session {day} or not two before it")
    p2, p1 = back
    return p2.close_at, p1.close_at - T29_BEFORE_CLOSE


def night2_windows(store: S.Store, day: dt.date) -> dict[str, tuple[dt.datetime, dt.datetime]]:
    """NO NEW INFORMATION's three windows for entry session D = `day` (PREREG-EVL-5 section 1.1), each ending at D's close
    decision time: (i) "named", articles knowable after T29 of P and at or before it ((lo, hi], `news_named`); (ii)
    "filed", 8-Ks knowable at or after P''s close decision time and before it ([lo, hi), `filings_window`: the close
    windows of P and of D); (iii) "bought", Form 4s knowable at or after 09:00 ET of P and before it ([lo, hi),
    `ins_buys_window`)."""
    d = C.session(store, day)
    back = C.previous(store, day, 2)
    if d is None or len(back) < 2:
        raise LookupError(f"no session {day} or not two before it")
    p2, p1 = back
    return {"named": (p1.close_at - T29_BEFORE_CLOSE, d.close_decide), "filed": (p2.close_decide, d.close_decide),
            "bought": (p1.open_cutoff, d.close_decide)}


def news_named(store: S.Store, lo: dt.datetime, hi: dt.datetime) -> list[dict[str, Any]]:
    """NO NEW INFORMATION (i)'s articles (PREREG-EVL-5 section 1.1): every ENEWS article KNOWABLE in (lo, hi], of any
    source and with ANY number of symbols, oldest first, each with `named` (its symbols, upper case), and NO
    registration floor. PREREG-EVL-1 section 3's non-live exclusion is applied exactly as `news_rows` applies it (a live
    article counts; a non-live, backfilled one counts only when its `updated_at` is at most NEWS_UPDATE_LIMIT after its
    `created_at`); an article whose symbols cannot be read names none."""
    rows = store.db.execute("SELECT * FROM news WHERE knowable_at>? AND knowable_at<=? ORDER BY knowable_at, id",
                            (S.iso(lo), S.iso(hi)))
    out = []
    for r in rows:
        if not r["live"] and r["updated_at"] and \
                S.parse_iso(r["updated_at"]) - S.parse_iso(r["created_at"]) > NEWS_UPDATE_LIMIT:
            continue  # backfilled and edited more than 10 minutes after publication (PREREG-EVL-1 section 3)
        try:
            symbols = json.loads(r["symbols"] or "[]")
        except ValueError:
            continue
        if isinstance(symbols, list):
            out.append(dict(r) | {"named": sorted({str(x).upper() for x in symbols if x is not None and str(x)})})
    return out


def ins_buys_window(store: S.Store, lo: dt.datetime, hi: dt.datetime) -> list[dict[str, Any]]:
    """NO NEW INFORMATION (iii)'s filings: the fetched Form 4s knowable in [lo, hi) with PREREG-EVL-2's INSIDER BUY
    (`ins_buys`' rule, `_insider_buy`), oldest first, with NO registration floor (PREREG-EVL-5 section 1.2: the sets
    that skip carry none). `ins_buys`, the earlier files' reader, is unchanged."""
    out = []
    for f in filings_window(store, "4", lo, hi):
        got = _insider_buy(store, f)
        if got is not None:
            out.append(got)
    return out


def ciks_by_ticker(tickers: Mapping[str, Iterable[tuple[str, str]]]) -> dict[str, set[str]]:
    """{ticker (upper case): the CIKs SEC's company_tickers.json maps it to} from a parsed copy (cik -> [(ticker,
    title)], league/events/universe.py `sec_tickers`): NO NEW INFORMATION (i) reads "a ticker that SEC's
    company_tickers.json (the copy D's decision reads) maps to the issuer's CIK"."""
    out: dict[str, set[str]] = {}
    for cik, rows in tickers.items():
        for ticker, _ in rows:
            if ticker:
                out.setdefault(str(ticker).upper(), set()).add(str(cik))
    return out


def named_ciks(articles: Iterable[Mapping[str, Any]], ciks_of: Mapping[str, set[str]]) -> set[str]:
    """NO NEW INFORMATION (i): the CIKs an article of `news_named` names (any of its symbols a ticker SEC's copy maps
    to the CIK)."""
    out: set[str] = set()
    for a in articles:
        for symbol in a.get("named") or ():
            out |= ciks_of.get(str(symbol).upper(), set())
    return out


def filed_ciks(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    """NO NEW INFORMATION (ii): the issuers (CIK, PREREG-EVL-1 section 2's as the lane stores it) of the fetched 8-Ks
    (form exactly `8-K`, ANY items) of `filings_window`'s rows."""
    return {str(r["cik"]) for r in rows if r.get("cik")}


def bought_ciks(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    """NO NEW INFORMATION (iii): the issuers of the Form 4s with an INSIDER BUY (`ins_buys_window`'s rows)."""
    return {str(r["cik"]) for r in rows if r.get("cik")}


def no_new_info(attention: Iterable[Mapping[str, Any]], named: set[str], filed: set[str], bought: set[str],
                symbol_of: Callable[[str], str | None]) -> list[Mapping[str, Any]]:
    """EVL-NEWS-NIGHT2-ON's rows of entry session D before its rule (PREREG-EVL-5 section 1.2): the attention articles of
    P (`attention`, each carrying its issuer's `cik` by D's tickers copy) whose one symbol is the issuer's ELIGIBLE ticker
    for D (`symbol_of(cik)`, None when the issuer is not eligible) and whose issuer has NO NEW INFORMATION on D: not in
    `named` (i), `filed` (ii) or `bought` (iii). The filters carry no registration condition; `select` keeps the events
    (knowable after the registration time) and applies the gap rule, one per issuer, the earliest."""
    skip = named | filed | bought
    out = []
    for a in attention:
        cik = a.get("cik")
        if not cik or str(cik) in skip:
            continue
        symbol = symbol_of(str(cik))
        if symbol is not None and symbol == a.get("symbol"):
            out.append(a)
    return out


def taken_close_5(ern_rows: Iterable[Mapping[str, Any]], day_articles: Iterable[Mapping[str, Any]], *,
                  symbol_of: Callable[[str], str | None], reaction: Callable[[Mapping[str, Any]], float | None],
                  day_reaction: Callable[[str], float | None],
                  news_answer: Callable[[Mapping[str, Any]], Mapping[str, Any] | None]) -> tuple[set[str], set[str]]:
    """TAKEN AT D'S CLOSE BY AN EARLIER ROW (PREREG-EVL-5 section 1.1), read with NO registration floor: (taken, waiting)
    CIK sets. An issuer is TAKEN (a) with an ERN(D) filing whose reaction is >= 1.04 (`reaction(row)`, None when a price
    is missing or the issuer is not eligible: then not taken by it), (b) with a DAY(D) article whose stored PROMPT-NEWS
    answer (`news_answer(article)`: the stored verdict row, None when none is stored) is `ok` with score >= 2, or (c) in
    DAY(D) with a day-news reaction >= 1.04 (`day_reaction(cik)`). DAY(D)'s articles are `day_articles` whose one symbol
    is the issuer's eligible ticker for D (`symbol_of`). An issuer not taken with a DAY(D) article that has no stored
    answer WAITS (the shadow rule; real money skips it instead: league/events/book.py). An answer `unparsed` or
    `refused`, or `ok` under 2, makes no issuer taken under (b)."""
    taken: set[str] = set()
    for r in ern_rows:
        cik = r.get("cik")
        if not cik or not items_of(r) & ERN_ITEMS:
            continue
        ratio = reaction(r)
        if ratio is not None and ratio >= REACT_RATIO:
            taken.add(str(cik))
    day: dict[str, list[Mapping[str, Any]]] = {}
    for a in day_articles:
        cik = a.get("cik")
        if not cik:
            continue
        symbol = symbol_of(str(cik))
        if symbol is not None and symbol == a.get("symbol"):
            day.setdefault(str(cik), []).append(a)
    unanswered: set[str] = set()
    for cik, articles in day.items():
        if cik not in taken:
            ratio = day_reaction(cik)
            if ratio is not None and ratio >= REACT_RATIO:
                taken.add(cik)
        for a in articles:
            got = news_answer(a)
            if got is None:
                unanswered.add(cik)
            elif got.get("status") == "ok" and got.get("score") is not None and int(got["score"]) >= READ_MIN_SCORE:
                taken.add(cik)
    return taken, unanswered - taken


def dropped_ciks(ern_rows: Iterable[Mapping[str, Any]], reaction: Callable[[Mapping[str, Any]], float | None]) -> set[str]:
    """The issuers with an ERN(D) filing whose reaction is <= 0.96 (PREREG-EVL-5 section 1.2, no registration floor):
    EVL-ERN-UNDER-ON and its control skip them."""
    out: set[str] = set()
    for r in ern_rows:
        cik = r.get("cik")
        if not cik or not items_of(r) & ERN_ITEMS:
            continue
        ratio = reaction(r)
        if ratio is not None and ratio <= DROP_RATIO:
            out.add(str(cik))
    return out


def close_rows_5(ern_rows: Iterable[Mapping[str, Any]], night2: Iterable[Mapping[str, Any]], *, taken: set[str],
                 waiting: set[str], dropped: set[str]) -> dict[str, list[Mapping[str, Any]]]:
    """PREREG-EVL-5's rows of entry session D before each program's own rule (section 1.2): {"ern-drop": the ERN(D)
    filings of issuers not TAKEN and not waiting; "ern-under": those of issuers also not in `dropped`; "news-night2":
    `no_new_info`'s articles}. An issuer that WAITS is held out of the earnings rows here; its decision is pending
    (league/events/run.py) until its DAY(D) answers are stored."""
    ern = [r for r in ern_rows if r.get("cik") and items_of(r) & ERN_ITEMS]
    drop = [r for r in ern if str(r["cik"]) not in taken and str(r["cik"]) not in waiting]
    under = [r for r in drop if str(r["cik"]) not in dropped]
    return {"ern-drop": drop, "ern-under": under, "news-night2": list(night2)}


def ins_triggers(store: S.Store, lo: dt.datetime, hi: dt.datetime, *,
                 since: dt.datetime | None = None) -> list[Mapping[str, Any]]:
    """Form 4 filings knowable in [lo, hi) that trigger EVL-INS-CLUSTER-O5 (a record; PREREG draft 2 section 6).

    The cluster at a filing F of issuer X: open-market purchases (code P, acquired A) whose transaction dates fall in
    the window, by >= 2 distinct reporting owners who are directors or officers of X, in >= 2 different filings, all
    filed within the 10 calendar days ending at F's acceptance, total shares x price >= $50,000. F triggers when the
    cluster holds at F, held at no earlier Form 4 of X inside F's window, and X has no trigger in the 10 calendar days
    before F. `since`: as `filings_in`'s."""
    out = []
    for f in filings_in(store, "4", lo, hi, since=since):
        accepted = S.parse_iso(f["accepted_at"])
        holds, value = _cluster(store, f["cik"], accepted)
        if not holds:
            continue
        if _earlier_trigger(store, f["cik"], accepted):
            continue
        out.append(dict(f) | {"cluster_value": value})
    return out


def ins_buys(store: S.Store, lo: dt.datetime, hi: dt.datetime, *,
             since: dt.datetime | None = None) -> list[Mapping[str, Any]]:
    """Form 4 filings knowable in [lo, hi) with PREREG-EVL-2's INSIDER BUY: a reporting owner who is a director or an
    officer of the issuer, and >= $50,000 of open-market purchases (code P, acquired A) dated within the 10 calendar
    days ending on the acceptance date (Eastern), each transaction counted once, a transaction with no price counting
    0. Each row carries its `purchase_value`, and (R3's role filter, league/events/births.py; no PREREG rule reads
    them) `by_director` and `by_officer`: whether a reporting owner is one. `since`: as `filings_in`'s."""
    out = []
    for f in filings_in(store, "4", lo, hi, since=since):
        got = _insider_buy(store, f)
        if got is not None:
            out.append(got)
    return out


def _insider_buy(store: S.Store, f: Mapping[str, Any]) -> dict[str, Any] | None:
    """One fetched Form 4 row `f` with PREREG-EVL-2's INSIDER BUY (`ins_buys`' rule), with its `purchase_value`,
    `by_director` and `by_officer`; None when it has none."""
    insider = store.db.execute("SELECT 1 FROM form4_owners WHERE accession=? AND (is_director OR is_officer) LIMIT 1",
                               (f["accession"],)).fetchone()
    if insider is None:
        return None
    roles = store.db.execute("SELECT MAX(COALESCE(is_director, 0) <> 0) AS d, MAX(COALESCE(is_officer, 0) <> 0) AS o "
                             "FROM form4_owners WHERE accession=?", (f["accession"],)).fetchone()
    accepted_day = S.parse_iso(f["accepted_at"]).astimezone(C.NY).date()
    first_day = (accepted_day - dt.timedelta(days=9)).isoformat()
    value = 0.0
    for t in store.db.execute("SELECT seq, tx_date, code, acquired, shares, price FROM form4_tx WHERE accession=? "
                              "ORDER BY seq", (f["accession"],)):
        if t["code"] != "P" or t["acquired"] != "A" or not t["tx_date"]:
            continue
        if not first_day <= str(t["tx_date"])[:10] <= accepted_day.isoformat():
            continue
        if t["shares"] is None or t["price"] is None:
            continue
        value += float(t["shares"]) * float(t["price"])
    if value >= INS_BUY_MIN_VALUE:
        return dict(f) | {"purchase_value": value, "by_director": bool(roles["d"]), "by_officer": bool(roles["o"])}
    return None


def _issuer_filings(store: S.Store, cik: str, lo: dt.datetime, hi: dt.datetime) -> list[Mapping[str, Any]]:
    return [dict(r) for r in store.db.execute(
        "SELECT accession, accepted_at FROM filings WHERE form='4' AND status='fetched' AND cik=? AND accepted_at>=? "
        "AND accepted_at<? ORDER BY accepted_at, accession", (cik, S.iso(lo), S.iso(hi)))]


def _earlier_trigger(store: S.Store, cik: str, at: dt.datetime) -> bool:
    """True when an earlier Form 4 of `cik` inside the 10 days before `at` already held a cluster. That one condition
    is both rules: the filing at `at` is not the first to meet the cluster, and any trigger less than 10 days before it
    (itself a filing that held one) falls inside the same 10 days."""
    for g in _issuer_filings(store, cik, at - INS_WINDOW, at):
        if _cluster(store, cik, S.parse_iso(g["accepted_at"]))[0]:
            return True
    return False


def _cluster(store: S.Store, cik: str, at: dt.datetime) -> tuple[bool, float]:
    start = at - INS_WINDOW
    first_day = start.astimezone(C.NY).date().isoformat()
    last_day = at.astimezone(C.NY).date().isoformat()
    rows = store.db.execute(
        "SELECT f.accession, o.owner_cik, o.is_director, o.is_officer, t.seq, t.tx_date, t.code, t.acquired, t.shares, "
        "t.price FROM filings f JOIN form4_owners o ON o.accession=f.accession JOIN form4_tx t ON t.accession=f.accession "
        "WHERE f.form='4' AND f.status='fetched' AND f.cik=? AND f.accepted_at>? AND f.accepted_at<=?",
        (cik, S.iso(start), S.iso(at))).fetchall()
    owners: set[str] = set()
    filings: set[str] = set()
    counted: set[tuple[str, int]] = set()
    value = 0.0
    for r in rows:
        if not (r["is_director"] or r["is_officer"]):
            continue
        if r["code"] != "P" or r["acquired"] != "A" or r["shares"] is None or r["price"] is None:
            continue
        if not r["tx_date"] or not first_day <= str(r["tx_date"])[:10] <= last_day:
            continue
        owners.add(r["owner_cik"])
        filings.add(r["accession"])
        if (r["accession"], r["seq"]) not in counted:   # a joint filing's owners share its transactions: count once
            counted.add((r["accession"], r["seq"]))
            value += float(r["shares"]) * float(r["price"])
    holds = len(owners) >= INS_MIN_OWNERS and len(filings) >= 2 and value >= INS_MIN_VALUE
    return holds, value


# ---------------------------------------------------------------------------------------------------- decisions
@dataclasses.dataclass
class Candidate:
    event: str
    cik: str
    symbol: str
    knowable_at: dt.datetime
    rank_key: float | None
    verdict_score: int | None
    row: Mapping[str, Any]


def _held_recently(store: S.Store, program: Program, cik: str, day: dt.date) -> bool:
    """PREREG-EVL-1 section 5's ONE POSITION PER ISSUER: the program holds the issuer, or held it within the last
    ISSUER_GAP_SESSIONS sessions, OR (the reading that trades less, amendment A72, fixed before any event settled) holds
    a written intent of it entering within the ISSUER_GAP_SESSIONS sessions after `day`: so an event decided late for an
    earlier session never adds a second position beside a later one already written, whatever the order of arrival."""
    back = C.previous(store, day, ISSUER_GAP_SESSIONS)
    since = back[0].day if back else day
    ahead = C.nth(store, day, ISSUER_GAP_SESSIONS + 1)
    until = ahead.day.isoformat() if ahead is not None else "9999-12-31"
    row = store.db.execute("SELECT 1 FROM intents WHERE program=? AND version=? AND cik=? AND status NOT LIKE 'skipped%' "
                           "AND exit_day>=? AND entry_day<=? LIMIT 1",
                           (program.id, program.version, cik, since.isoformat(), until)).fetchone()
    return row is not None


def write_intents(store: S.Store, program: Program, day: dt.date, candidates: Iterable[Candidate], *,
                  decided_at: dt.datetime, mode: str = "shadow", why: str | None = None) -> dict[str, int]:
    """One intent per candidate (oldest knowable first; a repeat issuer is skipped), idempotent per (program, event)."""
    entry = C.session(store, day)
    if entry is None:
        raise LookupError(day)
    if program.entry_at == "open":
        exit_session = C.nth(store, day, program.hold)
    else:  # a close entry exits `hold` sessions later, at that session's close or (PREREG-EVL-2) its open
        exit_session = C.nth(store, day, program.hold + 1)
    counts = {"planned": 0, "skipped": 0, "known": 0}
    taken: set[str] = set()
    for c in sorted(candidates, key=lambda c: (c.knowable_at, c.event)):
        if store.db.execute("SELECT 1 FROM intents WHERE program=? AND version=? AND event=?",
                            (program.id, program.version, c.event)).fetchone():
            counts["known"] += 1
            continue
        status = "planned"
        reason = why
        if exit_session is None:
            status, reason = "skipped:no-exit-session", why
        elif c.cik in taken or _held_recently(store, program, c.cik, day):
            status, reason = "skipped:issuer-held", why
        store.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                         "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                         "?, ?)",
                         (program.id, program.version, c.event, c.symbol, c.cik, S.iso(decided_at), day.isoformat(),
                          program.entry_at, (exit_session.day if exit_session else day).isoformat(), program.exit_at,
                          c.rank_key, mode, status, reason))
        counts["planned" if status == "planned" else "skipped"] += 1
        if status == "planned":
            taken.add(c.cik)
    return counts


#: Families whose events are news articles; "news", "news-day" and PREREG-EVL-4's "news-pm" rank by verdict score (one
#: per issuer per D, the highest score, then the earliest: `BEST_SCORE`), "news-react" takes the earliest (no model),
#: and PREREG-EVL-5's "news-night2" the issuer's earliest attention article (no model, ranked by the gap).
NEWS_FAMILIES = ("news", "news-day", "news-react", "news-pm", "news-night2")
#: The families whose one event per issuer per D is the highest stored score, then the earliest (their controls too):
#: PREREG-EVL-5's "ern-under" too (EVL-ERN-UNDER-ON and its control; a filing with no stored `ok` score ranks after
#: every one with it).
BEST_SCORE = ("news", "news-day", "news-pm", "ern-under")
#: The REACT families: the reaction (C1's ratio at T29) >= REACT_RATIO, ranked by it; a missing price takes nothing.
REACT_FAMILIES = ("ern-react", "news-react", "8k-react")


def select(program: Program, rows: Iterable[Mapping[str, Any]], *, eligible: Callable[[str], Mapping[str, Any] | None],
           verdict: Callable[[Mapping[str, Any]], int | None],
           reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None,
           guidance: Callable[[Mapping[str, Any]], str | None] | None = None,
           gap: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None) -> list[Candidate]:
    """The candidates `program` takes from already-windowed event rows. `eligible(cik)` -> universe row or None;
    `verdict(row)` -> the stored score (None when there is none, unparsed or refused); `reaction(row, universe_row)` ->
    C1's ratio (the close of the last SIP minute bar ending at or before 15:30 ET on day 0 over the last SIP daily close
    before the acceptance time), None when a price is missing (the event is then not taken); `guidance(row)` -> the
    stored PROMPT-DOC verdict's guidance (PREREG-EVL-2's GUIDE). An event knowable at or before the program's own
    registration time is never taken. PREREG-EVL-4's families take rows already windowed and cleared of the issuers its
    sets skip (`close_rows_4`): "8k-react" and "8k-day" apply EVL-8K-READ-O1's item rule (event `8k:<accession>`), the
    first ranked by the reaction (>= 1.04, no model), the second by the stored PROMPT-DOC score; "news-pm" ranks by the
    stored PROMPT-NEWS score, one per issuer (the highest, then the earliest), its `verdict` the stored reader alone.
    PREREG-EVL-5's families take rows already windowed and cleared of the issuers its sets skip (`close_rows_5`):
    "ern-drop" an ERN(D) filing whose reaction is <= 0.96 (ranked by the fall, 1 - reaction; no model); "ern-under" one
    whose reaction is above 0.96 and below 1.04 and, for EVL-ERN-UNDER-ON, whose stored PROMPT-DOC verdict is `ok` with
    score >= 2 (ranked by the score plus GUIDE_BONUS when its guidance is "raised"; its control takes every such filing,
    with or without a verdict), one per issuer (the highest score, then the earliest); "news-night2" the issuer's
    earliest attention article (event `news:<id>`), taken when its gap (`gap(row, universe_row)`: D's 09:30 minute's
    open over P's close, None when either price is missing) is >= 1.02, ranked by the gap.
    A registered birth (R3, `Program.born`) is selected by its own spec's rule (league/events/births.py `select`, the
    same callables); no PREREG program ever reaches it."""
    if program.spec is not None:
        from . import births as BI

        return BI.select(program, rows, eligible=eligible, verdict=verdict, reaction=reaction, guidance=guidance)
    out = []
    since = program.registered_at
    for row in rows:
        family = program.family
        if S.parse_iso(row.get("knowable_at")) <= since:
            continue
        if family in ("ern", "ern-react") or family in FAMILY_8K or family in FAMILY_ERN_5:
            items = items_of(row)
            if (family in ("ern", "ern-react") or family in FAMILY_ERN_5) and not items & ERN_ITEMS:
                continue
            if family in FAMILY_8K and (not items & OTHER_ITEMS or items & ERN_ITEMS):
                continue
            event = f"8k:{row['accession']}"
        elif family in ("ins", "ins-buy"):
            event = f"f4:{row['accession']}"
        else:
            event = f"news:{row['id']}"
        cik = row.get("cik") or row.get("issuer_cik")
        uni = eligible(cik) if cik else None
        if uni is None:
            continue
        if family in NEWS_FAMILIES and uni["symbol"] != row.get("symbol"):
            continue
        score = verdict(row) if (program.reads or family in BEST_SCORE) else None
        if program.reads:
            if score is None:
                continue
            if program.rule == "min2" and score < READ_MIN_SCORE:
                continue
            if program.rule == "top" and score != TOP_SCORE:
                continue
            if program.rule == "guide" and (score < GUIDE_MIN_SCORE or guidance is None or guidance(row) != "raised"):
                continue
        rank = float(score) if score is not None else None
        if family in REACT_FAMILIES:
            ratio = reaction(row, uni) if reaction is not None else None
            if ratio is None or ratio < REACT_RATIO:
                continue
            rank = ratio
        if family == "ern-drop":        # PREREG-EVL-5: the reaction <= 0.96, ranked by the fall
            ratio = reaction(row, uni) if reaction is not None else None
            if ratio is None or ratio > DROP_RATIO:
                continue
            rank = 1.0 - ratio
        if family == "ern-under":       # PREREG-EVL-5: above 0.96 and below 1.04 (the verdict rule above, for the READ row)
            ratio = reaction(row, uni) if reaction is not None else None
            if ratio is None or not DROP_RATIO < ratio < REACT_RATIO:
                continue
            if program.reads and score is not None:
                rank = float(score) + (GUIDE_BONUS if guidance is not None and guidance(row) == "raised" else 0.0)
        if family == "news-night2":     # PREREG-EVL-5: the gap >= 1.02, ranked by it
            got = gap(row, uni) if gap is not None else None
            if got is None or got < GAP_RATIO:
                continue
            rank = got
        if family == "ins":
            rank = float(row.get("cluster_value") or 0.0)
        if family == "ins-buy":
            rank = float(row.get("purchase_value") or 0.0)
        out.append(Candidate(event, cik, uni["symbol"], S.parse_iso(row.get("knowable_at")), rank, score, row))
    if program.family in BEST_SCORE:
        best: dict[str, Candidate] = {}
        for c in out:
            have = best.get(c.cik)
            def order(x: Candidate) -> tuple[int, float]:
                return (x.verdict_score if x.verdict_score is not None else -9, -x.knowable_at.timestamp())
            if have is None or order(c) > order(have):
                best[c.cik] = c
        out = list(best.values())
    if program.family == "news-night2":     # (PREREG-EVL-5: the issuer's one event, its earliest attention article)
        first: dict[str, Candidate] = {}
        for c in out:
            if c.cik not in first or (c.knowable_at, c.event) < (first[c.cik].knowable_at, first[c.cik].event):
                first[c.cik] = c
        out = list(first.values())
    return out


__all__ = ["PROGRAMS", "BY_ID", "BY_KEY", "SEATING", "PREREG_PROGRAMS", "PREREG_SEATING", "BIRTHS", "load_births",
           "REGISTERED_AT_3", "REGISTERED_AT_4", "SEATING_PREREGS", "Program", "Candidate", "REGISTERED_AT",
           "REGISTERED_AT_2", "registered", "open_window", "close_window", "news_window", "day_news_window", "filings_in",
           "news_in", "ins_triggers", "ins_buys", "select", "write_intents", "items_of", "NEWS_FAMILIES", "BEST_SCORE",
           "REACT_FAMILIES", "FAMILY_8K", "CLOSE_FAMILIES_4", "filings_window", "news_rows", "family_8k", "ern_ciks",
           "day_ciks", "f8k_ciks", "excluded", "close_rows_4", "REGISTERED_AT_5", "DROP_RATIO", "GAP_RATIO", "GUIDE_BONUS",
           "FAMILY_ERN_5", "CLOSE_FAMILIES_5", "attention_window", "night2_windows", "news_named", "ins_buys_window",
           "ciks_by_ticker", "named_ciks", "filed_ciks", "bought_ciks", "no_new_info", "taken_close_5", "dropped_ciks",
           "close_rows_5"]


# ---------------------------------------------------------------------------------------------------- PREREG-EVL-8
#: PREREG-EVL-8's REGISTRATION TIME (its preamble, A92's method: the latest of its commit's time, the pushing client's
#: clock after the push of the tag `prereg-evl-8` returned and GitHub's activity time for the branch `prereg/evl-8`),
#: THE ONE CONSTANT THE FREEZE SETS (the captain's amendment that pins it as REGISTERED_AT_8). NONE UNTIL THEN: this
#: file's programs are in no registry (`rows_8`), so nothing of it decides, trades or is charged, and nothing of the
#: lane moves (league/events/px.py and meta.py check `registers_8` before every write).
REGISTERED_AT_8: str | None = None
#: PREREG-EVL-6's registration time as the captain's A116 records it (tag prereg-evl-6, commit 4ae9017a): PREREG-EVL-8
#: registers anything only when it is EARLIER than REGISTERED_AT_8 (its preamble: "This file is frozen only after
#: PREREG-EVL-6 (REGISTERED_AT_6 < REGISTERED_AT_8)"; `registers_8`). Kept here beside this file's rows so they read no
#: other branch's constant; a test holds it equal to `REGISTERED_AT_6` wherever the tree carries PREREG-EVL-6's code.
REGISTERED_AT_6_FOR_8 = "2026-10-22T12:24:50Z"
#: The file that registers this file's rows, and its families: the PX lane's three seats and two controls (part A,
#: league/events/px.py decides them, never `select`), the two meta-learners (part B, league/events/meta.py).
FILE_8 = 8
PX_SEAT_FAMILIES = ("px-drop-on", "px-surge-on", "px-gap-o1")
PX_CONTROL_FAMILIES = ("px-ctrl-on", "px-ctrl-o1")
PX_FAMILIES = PX_SEAT_FAMILIES + PX_CONTROL_FAMILIES
META_FAMILIES = ("meta-o1", "meta-on")
FAMILIES_8 = PX_FAMILIES + META_FAMILIES


@dataclasses.dataclass(frozen=True)
class Program8(Program):
    """A PREREG-EVL-8 version (part A's seats and controls, part B's meta-learners): its own registration time,
    REGISTERED_AT_8 (never another file's), and its seat only when this file registers anything (`registers_8`). Its
    rule is league/events/px.py's or meta.py's pinned procedure, never `select`'s: no verdict read by the shadow rule
    (`reads` False). PREREG-EVL-2's limit at entry applies (league/events/score.py: prereg >= 2).

    `evl6` is False: PREREG-EVL-6's own run machinery (league/events/screen.py `_run_v6` on release 1019i) never judges
    these versions, because PREREG-EVL-8 section 5 reads the frozen text's 14 as THE OPEN CAP OF THE VERSION'S BAND
    (F4: 4 for a PX run in learning, 8 for a meta-learner's run, 14 for a Probe stay, 8 for a Sized stay), which
    PREREG-EVL-6's code holds at 14 for its own versions. THE ONE NARROW INTERFACE is league/events/screen8.py: this
    file's judge, PREREG-EVL-6 sections 1.2-3 as frozen with that cap (`screen8.judge_blocks`), new code beside
    screen.py's, PREREG-EVL-1 to -7's paths intact (PREREG-EVL-8 section 5.3)."""

    @property
    def registered_at(self) -> dt.datetime:
        if REGISTERED_AT_8 is None:
            raise RuntimeError("PREREG-EVL-8 is not pinned: none of its programs decides before its registration time")
        return S.parse_iso(REGISTERED_AT_8)

    @property
    def can_seat(self) -> bool:
        return self.seatable and registers_8()

    @property
    def evl6(self) -> bool:
        return False

    @property
    def px(self) -> bool:
        """Part A's (a PX seat or control)."""
        return self.family in PX_FAMILIES

    @property
    def meta(self) -> bool:
        """Part B's (a meta-learner)."""
        return self.family in META_FAMILIES


#: SECTION 3.1 AND 7.1'S PROGRAMS, VERSION 1 EACH, in ROOM's order (section 4.2: PX-DROP-ON, PX-SURGE-ON, PX-GAP-O1,
#: EVL-META-O1, EVL-META-ON), then the two controls (free records, PREREG-EVL-1 section 7: never seated, never
#: charged). Hold 1 each: an ON row enters at D's close and exits at D+1's open; an O1 row enters at D's open and exits at
#: D's close. The meta-learners' POOL records write no intents and are no rows here (league/events/meta.py).
ROWS_8: tuple[Program8, ...] = (
    Program8("PX-DROP-ON", 1, True, "px-drop-on", "close", 1, False, exit_at="open", rule="px", prereg=FILE_8),
    Program8("PX-SURGE-ON", 1, True, "px-surge-on", "close", 1, False, exit_at="open", rule="px", prereg=FILE_8),
    Program8("PX-GAP-O1", 1, True, "px-gap-o1", "open", 1, False, rule="px", prereg=FILE_8),
    Program8("EVL-META-O1", 1, True, "meta-o1", "open", 1, False, rule="mrl", prereg=FILE_8),
    Program8("EVL-META-ON", 1, True, "meta-on", "close", 1, False, exit_at="open", rule="mrl", prereg=FILE_8),
    Program8("CTRL-PX-ALL-ON", 1, False, "px-ctrl-on", "close", 1, False, exit_at="open", rule="px", prereg=FILE_8),
    Program8("CTRL-PX-ALL-O1", 1, False, "px-ctrl-o1", "open", 1, False, rule="px", prereg=FILE_8),
)


def registers_8() -> bool:
    """Whether PREREG-EVL-8 registers anything: REGISTERED_AT_8 is pinned and PREREG-EVL-6's registration time is
    earlier than it. Never True on an unreadable time (fail closed)."""
    if REGISTERED_AT_8 is None:
        return False
    try:
        return S.parse_iso(REGISTERED_AT_6_FOR_8) < S.parse_iso(REGISTERED_AT_8)
    except (TypeError, ValueError):
        return False


def rows_8() -> tuple[Program8, ...]:
    """This file's rows in force: all seven when it registers anything (`registers_8`), else none."""
    return ROWS_8 if registers_8() else ()


def is_8(program: Any) -> bool:
    """Whether a Program row (or an id) is one of PREREG-EVL-8's, pinned or not."""
    pid = getattr(program, "id", program)
    return any(p.id == pid for p in ROWS_8)


def is_px8(program: Any) -> bool:
    """Whether a Program row (or an id) is one of part A's (a PX seat or control), pinned or not."""
    pid = getattr(program, "id", program)
    return any(p.id == pid and p.px for p in ROWS_8)


def is_meta8(program: Any) -> bool:
    """Whether a Program row (or an id) is one of part B's meta-learners, pinned or not."""
    pid = getattr(program, "id", program)
    return any(p.id == pid and p.meta for p in ROWS_8)


def refresh_8() -> tuple[Program8, ...]:
    """THE REGISTRIES WITH PREREG-EVL-8 AS PINNED (`rows_8`): PREREG_PROGRAMS and PREREG_SEATING are every earlier
    file's rows (whatever this tree holds of PREREG-EVL-1 to -7, in their order) then this file's; PROGRAMS, BY_KEY,
    BY_ID and SEATING are rebound with R3's births loaded last after them (as `load_births` binds them), so ROOM's
    order (league/events/book.py `order_of`) puts this file's seats after every earlier file's row and before R3's
    births (section 4.2, A101), and no earlier row's place, rule or judge moves. Idempotent: this file's rows are taken
    out first and appended again, so it composes with any earlier file's own refresh run before it. Run at import and
    by a test that pins REGISTERED_AT_8. Returns the rows in force."""
    global PROGRAMS, BY_KEY, BY_ID, SEATING, PREREG_PROGRAMS, PREREG_SEATING
    rows = rows_8()
    with _LOAD:
        PREREG_PROGRAMS = tuple(p for p in PREREG_PROGRAMS if not is_8(p)) + rows
        PREREG_SEATING = tuple(p for p in PREREG_SEATING if not is_8(p)) + tuple(p for p in rows if p.can_seat)
        programs = PREREG_PROGRAMS + BIRTHS
        PROGRAMS = programs
        BY_KEY = {(p.id, p.version): p for p in programs}
        BY_ID = {p.id: p for p in programs if p.version == 1}
        SEATING = PREREG_SEATING + tuple(p for p in BIRTHS if p.can_seat)
    return rows


refresh_8()

__all__ += ["REGISTERED_AT_8", "REGISTERED_AT_6_FOR_8", "FILE_8", "PX_SEAT_FAMILIES", "PX_CONTROL_FAMILIES",
            "PX_FAMILIES", "META_FAMILIES", "FAMILIES_8", "Program8", "ROWS_8", "registers_8", "rows_8", "is_8",
            "is_px8", "is_meta8", "refresh_8"]
