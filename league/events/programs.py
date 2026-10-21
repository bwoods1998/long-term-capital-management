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
Eligibility (league.events.universe) is decided before any verdict is asked, so verdicts are paid only for eligible
issuers; controls take every eligible event of their program's family, any verdict.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import threading
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
#: The files whose seatable rows may trade real money: PREREG-EVL-3 (version 2 of the nine seatable programs of
#: PREREG-EVL-1 and -2) and PREREG-EVL-4 (version 1 of its three: its ids are new, so their version 1 is registered
#: with PREREG-EVL-3's bands, section 2). Version 1 of PREREG-EVL-1's and -2's ids, records and controls never seat.
SEATING_PREREGS = (3, 4)

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


@dataclasses.dataclass(frozen=True)
class Program:
    id: str
    version: int
    seatable: bool
    family: str          # ern | ern-react | 8k | ins | news | ins-buy | news-day | news-react | 8k-react | 8k-day | news-pm
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
        -2's, -3's or -4's; never another file's (PREREG-EVL-4: "not PREREG-EVL-1's, -2's or -3's"). A file this code
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
        raise ValueError(f"no registration time is pinned for PREREG-EVL-{self.prereg}")

    @property
    def can_seat(self) -> bool:
        """Whether this version may ever trade real money: PREREG-EVL-3 section 1, version 2 of the nine seatable
        programs (prereg 3), and PREREG-EVL-4 section 2, version 1 of its three seatable programs (prereg 4: its seating
        version). Version 1 of PREREG-EVL-1's and -2's programs stays a shadow record with its own screen, never seated;
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
#: Every program version by (id, version).
BY_KEY = {(p.id, p.version): p for p in PROGRAMS}
#: Version 1 of every program by id (the records and controls exist at version 1 only).
BY_ID = {p.id: p for p in PROGRAMS if p.version == 1}
#: The versions that may ever trade real money (PREREG-EVL-3 section 1, PREREG-EVL-4 section 2), in the tables' order:
#: the nine version 2 rows (PREREG-EVL-1's four, then PREREG-EVL-2's five), then PREREG-EVL-4's three (version 1).
SEATING = tuple(p for p in PROGRAMS if p.can_seat)
#: THE PREREG PROGRAMS (PREREG-EVL-1, -2, -3 and -4), fixed: `load_births` keeps them first and unchanged, and adds
#: the registered births after them (after PREREG-EVL-4's rows, so ROOM's order puts every PREREG program first).
PREREG_PROGRAMS = PROGRAMS
PREREG_SEATING = SEATING
#: R3's registered births as last loaded from a store (`load_births`), in registration order, each READ birth followed
#: by its derived control (a record).
BIRTHS: tuple[Program, ...] = ()
_LOAD = threading.Lock()


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
    of it (`.db`); a store without the table, or one that cannot be read, loads none (and a load that would give two
    rows one key loads none); None unloads every birth. Returns the births loaded."""
    global PROGRAMS, BY_KEY, BY_ID, SEATING, BIRTHS
    from . import births as BI

    try:
        born = () if store is None else tuple(BI.registered_programs(store))
    except Exception:  # noqa: BLE001 - an unreadable births table seats nothing (fail closed), the PREREG rows stand
        born = ()
    with _LOAD:
        programs = PREREG_PROGRAMS + born
        by_key = {(p.id, p.version): p for p in programs}
        if len(by_key) != len(programs):
            born, programs = (), PREREG_PROGRAMS
            by_key = {(p.id, p.version): p for p in programs}
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
        insider = store.db.execute("SELECT 1 FROM form4_owners WHERE accession=? AND (is_director OR is_officer) LIMIT 1",
                                   (f["accession"],)).fetchone()
        if insider is None:
            continue
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
            out.append(dict(f) | {"purchase_value": value, "by_director": bool(roles["d"]), "by_officer": bool(roles["o"])})
    return out


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
#: per issuer per D, the highest score, then the earliest: `BEST_SCORE`), "news-react" takes the earliest (no model).
NEWS_FAMILIES = ("news", "news-day", "news-react", "news-pm")
#: The families whose one event per issuer per D is the highest stored score, then the earliest (their controls too).
BEST_SCORE = ("news", "news-day", "news-pm")
#: The REACT families: the reaction (C1's ratio at T29) >= REACT_RATIO, ranked by it; a missing price takes nothing.
REACT_FAMILIES = ("ern-react", "news-react", "8k-react")


def select(program: Program, rows: Iterable[Mapping[str, Any]], *, eligible: Callable[[str], Mapping[str, Any] | None],
           verdict: Callable[[Mapping[str, Any]], int | None],
           reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None,
           guidance: Callable[[Mapping[str, Any]], str | None] | None = None) -> list[Candidate]:
    """The candidates `program` takes from already-windowed event rows. `eligible(cik)` -> universe row or None;
    `verdict(row)` -> the stored score (None when there is none, unparsed or refused); `reaction(row, universe_row)` ->
    C1's ratio (the close of the last SIP minute bar ending at or before 15:30 ET on day 0 over the last SIP daily close
    before the acceptance time), None when a price is missing (the event is then not taken); `guidance(row)` -> the
    stored PROMPT-DOC verdict's guidance (PREREG-EVL-2's GUIDE). An event knowable at or before the program's own
    registration time is never taken. PREREG-EVL-4's families take rows already windowed and cleared of the issuers its
    sets skip (`close_rows_4`): "8k-react" and "8k-day" apply EVL-8K-READ-O1's item rule (event `8k:<accession>`), the
    first ranked by the reaction (>= 1.04, no model), the second by the stored PROMPT-DOC score; "news-pm" ranks by the
    stored PROMPT-NEWS score, one per issuer (the highest, then the earliest), its `verdict` the stored reader alone.
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
        if family in ("ern", "ern-react") or family in FAMILY_8K:
            items = items_of(row)
            if family in ("ern", "ern-react") and not items & ERN_ITEMS:
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
    return out


__all__ = ["PROGRAMS", "BY_ID", "BY_KEY", "SEATING", "PREREG_PROGRAMS", "PREREG_SEATING", "BIRTHS", "load_births",
           "REGISTERED_AT_3", "REGISTERED_AT_4", "SEATING_PREREGS", "Program", "Candidate", "REGISTERED_AT",
           "REGISTERED_AT_2", "registered", "open_window", "close_window", "news_window", "day_news_window", "filings_in",
           "news_in", "ins_triggers", "ins_buys", "select", "write_intents", "items_of", "NEWS_FAMILIES", "BEST_SCORE",
           "REACT_FAMILIES", "FAMILY_8K", "CLOSE_FAMILIES_4", "filings_window", "news_rows", "family_8k", "ern_ciks",
           "day_ciks", "f8k_ciks", "excluded", "close_rows_4"]
