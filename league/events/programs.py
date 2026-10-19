"""The pre-registered programs of PREREG-EVL-1 section 6, and the shadow decisions that apply them.

Nothing here may change for a registered program: a change is a new version with its own registration time. The
registration time is the commit time of docs/prereg/PREREG-EVL-1.md on `prereg/evl-1` (pinned below once committed);
an event counts only when its knowable time is after it.

Decision windows (league.events.calendar):
- OPEN entry on session D takes exactly the events knowable in [P 09:00 ET, D 09:00 ET), P the session before D
  (these are the events whose "first session whose 09:00 ET is after the knowable time" is D).
- C1's day 0 is D for exactly the events knowable in [P's close decision, D's close decision).
- NEWS-READ on D takes single-symbol articles created after P's 16:00 ET and before D's 09:00 ET.
Eligibility (league.events.universe) is decided before any verdict is asked, so verdicts are paid only for eligible
issuers; controls take every eligible event of their program's family, any verdict.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from typing import Any, Callable, Iterable, Mapping

from . import calendar as C
from . import store as S

#: The registration time (UTC): the prereg's commit time on `prereg/evl-1`. None refuses every decision.
REGISTERED_AT: str | None = None

ERN_ITEMS = frozenset({"2.02"})
OTHER_ITEMS = frozenset({"1.01", "2.01", "7.01", "8.01"})
READ_MIN_SCORE = 2
REACT_RATIO = 1.04
INS_WINDOW = dt.timedelta(days=10)
INS_MIN_OWNERS = 2
INS_MIN_VALUE = 50_000.0
ISSUER_GAP_SESSIONS = 5
NEWS_UPDATE_LIMIT = dt.timedelta(minutes=10)


@dataclasses.dataclass(frozen=True)
class Program:
    id: str
    version: int
    seatable: bool
    family: str          # ern | ern-react | 8k | ins | news
    entry_at: str        # open | close
    hold: int            # sessions held (block length); C1 enters at day 0's close and exits at the next close
    reads: bool          # needs a verdict score >= READ_MIN_SCORE

    @property
    def key(self) -> tuple[str, int]:
        return (self.id, self.version)


PROGRAMS = (
    Program("EVL-ERN-READ-O1", 1, True, "ern", "open", 1, True),
    Program("EVL-ERN-READ-O3", 1, True, "ern", "open", 3, True),
    Program("EVL-ERN-REACT-C1", 1, True, "ern-react", "close", 1, False),
    Program("EVL-8K-READ-O1", 1, True, "8k", "open", 1, True),
    Program("EVL-INS-CLUSTER-O5", 1, True, "ins", "open", 5, False),
    Program("EVL-NEWS-READ-O1", 1, True, "news", "open", 1, True),
    Program("EVL-CTRL-ERN-ALL-O1", 1, False, "ern", "open", 1, False),
    Program("EVL-CTRL-8K-ALL-O1", 1, False, "8k", "open", 1, False),
    Program("EVL-CTRL-NEWS-ALL-O1", 1, False, "news", "open", 1, False),
)
BY_ID = {p.id: p for p in PROGRAMS}


def registered() -> dt.datetime:
    if REGISTERED_AT is None:
        raise RuntimeError("PREREG-EVL-1 is not pinned: no decision is made before its registration time")
    return S.parse_iso(REGISTERED_AT)


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
    return prior[0].close_at, d.open_cutoff  # after P's 16:00 ET (its close) and before D's 09:00 ET


# ---------------------------------------------------------------------------------------------------- events
def filings_in(store: S.Store, form: str, lo: dt.datetime, hi: dt.datetime) -> list[Mapping[str, Any]]:
    """Fetched filings of `form` knowable in [lo, hi) and after the registration time, oldest first."""
    lo = max(lo, registered())
    rows = store.db.execute("SELECT * FROM filings WHERE form=? AND status='fetched' AND knowable_at>=? AND knowable_at<? "
                            "ORDER BY knowable_at, accession", (form, S.iso(lo), S.iso(hi)))
    return [dict(r) for r in rows if S.parse_iso(r["knowable_at"]) > registered()]


def items_of(row: Mapping[str, Any]) -> set[str]:
    try:
        return set(json.loads(row.get("items") or "[]"))
    except ValueError:
        return set()


def news_in(store: S.Store, lo: dt.datetime, hi: dt.datetime) -> list[Mapping[str, Any]]:
    """Single-symbol articles created in (lo, hi), knowable after the registration time, oldest first."""
    rows = store.db.execute("SELECT * FROM news WHERE created_at>? AND created_at<? ORDER BY created_at, id",
                            (S.iso(lo), S.iso(hi)))
    out = []
    for r in rows:
        if S.parse_iso(r["knowable_at"]) <= registered():
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


def ins_triggers(store: S.Store, lo: dt.datetime, hi: dt.datetime) -> list[Mapping[str, Any]]:
    """Form 4 filings knowable in [lo, hi) that FIRST complete an insider cluster (PREREG section 6, INS-CLUSTER).

    The cluster at a filing F of issuer X: open-market purchases (code P, acquired A) by >= 2 distinct reporting owners
    who are directors or officers of X, in Form 4s of X accepted within the 10 calendar days ending at F's acceptance,
    total shares x price >= $50,000. F triggers when the cluster holds at F and held at no earlier Form 4 of X in that
    window."""
    out = []
    for f in filings_in(store, "4", lo, hi):
        accepted = S.parse_iso(f["accepted_at"])
        holds, value = _cluster(store, f["cik"], accepted)
        if not holds:
            continue
        earlier = store.db.execute("SELECT accession, accepted_at FROM filings WHERE form='4' AND status='fetched' AND cik=? "
                                   "AND accepted_at>=? AND accepted_at<? ORDER BY accepted_at",
                                   (f["cik"], S.iso(accepted - INS_WINDOW), S.iso(accepted))).fetchall()
        if any(_cluster(store, f["cik"], S.parse_iso(e["accepted_at"]))[0] for e in earlier):
            continue
        out.append(dict(f) | {"cluster_value": value})
    return out


def _cluster(store: S.Store, cik: str, at: dt.datetime) -> tuple[bool, float]:
    rows = store.db.execute(
        "SELECT f.accession, f.accepted_at, o.owner_cik, o.is_director, o.is_officer, t.code, t.acquired, t.shares, t.price "
        "FROM filings f JOIN form4_owners o ON o.accession=f.accession JOIN form4_tx t ON t.accession=f.accession "
        "WHERE f.form='4' AND f.status='fetched' AND f.cik=? AND f.accepted_at>? AND f.accepted_at<=?",
        (cik, S.iso(at - INS_WINDOW), S.iso(at))).fetchall()
    owners: set[str] = set()
    value = 0.0
    per_filing_owners: dict[str, set[str]] = {}
    for r in rows:
        if not (r["is_director"] or r["is_officer"]):
            continue
        if r["code"] != "P" or r["acquired"] != "A" or r["shares"] is None or r["price"] is None:
            continue
        per_filing_owners.setdefault(r["accession"], set()).add(r["owner_cik"])
    # a filing's purchases count once per transaction (a joint filing's owners share its transactions)
    seen_tx: set[tuple[str, float, float]] = set()
    for r in rows:
        if r["accession"] not in per_filing_owners or r["code"] != "P" or r["acquired"] != "A":
            continue
        if r["shares"] is None or r["price"] is None:
            continue
        tx = (r["accession"], float(r["shares"]), float(r["price"]))
        if tx in seen_tx:
            continue
        seen_tx.add(tx)
        value += float(r["shares"]) * float(r["price"])
    for who in per_filing_owners.values():
        owners |= who
    return len(owners) >= INS_MIN_OWNERS and value >= INS_MIN_VALUE, value


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
    back = C.previous(store, day, ISSUER_GAP_SESSIONS)
    since = back[0].day if back else day
    row = store.db.execute("SELECT 1 FROM intents WHERE program=? AND version=? AND cik=? AND status NOT LIKE 'skipped%' "
                           "AND exit_day>=? AND entry_day<=? LIMIT 1",
                           (program.id, program.version, cik, since.isoformat(), day.isoformat())).fetchone()
    return row is not None


def write_intents(store: S.Store, program: Program, day: dt.date, candidates: Iterable[Candidate], *,
                  decided_at: dt.datetime, mode: str = "shadow", why: str | None = None) -> dict[str, int]:
    """One intent per candidate (oldest knowable first; a repeat issuer is skipped), idempotent per (program, event)."""
    entry = C.session(store, day)
    if entry is None:
        raise LookupError(day)
    if program.entry_at == "open":
        exit_session = C.nth(store, day, program.hold)
    else:
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
                         "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'close', ?, ?, "
                         "?, ?)",
                         (program.id, program.version, c.event, c.symbol, c.cik, S.iso(decided_at), day.isoformat(),
                          program.entry_at, (exit_session.day if exit_session else day).isoformat(), c.rank_key, mode,
                          status, reason))
        counts["planned" if status == "planned" else "skipped"] += 1
        if status == "planned":
            taken.add(c.cik)
    return counts


def select(program: Program, rows: Iterable[Mapping[str, Any]], *, eligible: Callable[[str], Mapping[str, Any] | None],
           verdict: Callable[[Mapping[str, Any]], int | None],
           reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None) -> list[Candidate]:
    """The candidates `program` takes from already-windowed event rows. `eligible(cik)` -> universe row or None;
    `verdict(row)` -> the stored score (None when there is none, unparsed or refused); `reaction(row, universe_row)` ->
    C1's ratio (the close of the last SIP minute bar ending at or before 15:30 ET on day 0 over the last SIP daily close
    before the acceptance time), None when a price is missing (the event is then not taken)."""
    out = []
    for row in rows:
        family = program.family
        if family in ("ern", "ern-react", "8k"):
            items = items_of(row)
            if family in ("ern", "ern-react") and not items & ERN_ITEMS:
                continue
            if family == "8k" and (not items & OTHER_ITEMS or items & ERN_ITEMS):
                continue
            event = f"8k:{row['accession']}"
        elif family == "ins":
            event = f"f4:{row['accession']}"
        else:
            event = f"news:{row['id']}"
        cik = row.get("cik") or row.get("issuer_cik")
        uni = eligible(cik) if cik else None
        if uni is None:
            continue
        if family == "news" and uni["symbol"] != row.get("symbol"):
            continue
        score = verdict(row) if (program.reads or family == "news") else None
        if program.reads and (score is None or score < READ_MIN_SCORE):
            continue
        rank = float(score) if score is not None else None
        if family == "ern-react":
            ratio = reaction(row, uni) if reaction is not None else None
            if ratio is None or ratio < REACT_RATIO:
                continue
            rank = ratio
        if family == "ins":
            rank = float(row.get("cluster_value") or 0.0)
        out.append(Candidate(event, cik, uni["symbol"], S.parse_iso(row.get("knowable_at")), rank, score, row))
    if program.family == "news":
        best: dict[str, Candidate] = {}
        for c in out:
            have = best.get(c.cik)
            def order(x: Candidate) -> tuple[int, float]:
                return (x.verdict_score if x.verdict_score is not None else -9, -x.knowable_at.timestamp())
            if have is None or order(c) > order(have):
                best[c.cik] = c
        out = list(best.values())
    return out


__all__ = ["PROGRAMS", "BY_ID", "Program", "Candidate", "REGISTERED_AT", "registered", "open_window", "close_window",
           "news_window", "filings_in", "news_in", "ins_triggers", "select", "write_intents", "items_of"]
