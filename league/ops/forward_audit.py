"""The `forward_audit` job: the morning marks of the forward record, and the registry's chain check (release E3).

Owner: B (league/ops/E3_INTERFACES.md). Protected. 25 minutes before each open (after the equity book's morning
re-fetch of the last decision's bars, A8.11); in a pause too. It reads the live book read-only and writes only events
of `<state>/forward.sqlite` (league/ops/forward_db.py).

- THE AUDIT MARKS: for each bar of the live book that its morning re-fetch found different from the one a decision
  used, and each registered program whose NEEDS hold the symbol and whose forward days hold the day, one
  `audit_mismatch` event (once a (pid, day)). A marked day leaves the program's COUNTED days
  (`forward_db.counted_days`); its row stays. A program's forward days hold a day from its `first_day` on, whether its
  row for that day is written yet or not (a program left stale that night is marked before its row comes), stopped or
  not. A CONTROL IS NEVER MARKED: it reads no bar and decides nothing.
- WHICH BARS DIFFERED (`mismatches`), read from the book as E1 built it (league/equity/live.py `_audit`):
  - THE NOTE: the book's own record of each audit that failed, kv `eq_bars_audit` = {day: {"symbols": [the symbols
    whose bars differed], "at"}}, kept for its last 30 such days. A day the note names is marked for THOSE symbols.
  - THE ROWS: `eq_bars.audit` "mismatch". A day the note does not name is marked for every symbol with such a row.
  WHY THE NOTE FIRST (measured on E1's own book, two symbols fetched, one differing): that evening's fetch, which
  writes the whole history again, sets a row whose values changed back to unaudited: the raw row of the symbol that
  did differ. Read from the rows alone, a morning that could not read the book would find the next day a guilty row
  gone. The note names what differed and keeps it, so a morning that was missed is made up on a later one. (When this
  module was written the book also marked EVERY `eq_bars` row of the day when any one symbol differed, so a program
  that held only a symbol whose bar was right would have lost the day by its rows; E1's review made the mark each
  audited symbol's own verdict, "ok" or "mismatch", and a test here holds the book to that. A note the book writes
  for a volume-only difference names no symbol: its day is read from the rows, which then say "ok".)
- THE CHAIN: `forward_db.verify_chain` -> one `chain_ok` or `chain_broken` event, and for a broken chain a
  `ctx.alert("warning", ...)` (owner step: stop the forward jobs and compare with the backup). The alert's text
  holds ids, counts and dates only.

A FAILURE OF THE HOUSE NEVER MARKS A PROGRAM: a book that cannot be read marks nobody (a warning, and the receipt says
`marks` "unread"); the chain is still checked.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from . import forward_db, guard

#: The live book (league/equity/live.py: `eq_bars`), under the state root.
LIVE_DB = "live.sqlite"
#: `eq_bars.audit` of a bar the book's morning re-fetch found different.
MISMATCH = "mismatch"
#: The book's kv key of THE NOTE (the module docstring).
NOTE_KEY = "eq_bars_audit"


def _noted(db: sqlite3.Connection) -> dict[str, set[str]]:
    """THE NOTE (the module docstring): {day: the symbols the book's audit of that day found different}. An entry that
    is not {"symbols": [a symbol, ...]} is left out (its day is then read from THE ROWS); {} with no note at all."""
    row = db.execute("SELECT value FROM kv WHERE key=?", (NOTE_KEY,)).fetchone()
    try:
        note = json.loads(row[0]) if row is not None else None
    except (TypeError, ValueError):
        note = None
    out: dict[str, set[str]] = {}
    for day, entry in (note.items() if isinstance(note, Mapping) else ()):
        symbols = entry.get("symbols") if isinstance(entry, Mapping) else None
        if isinstance(symbols, (list, tuple)) and symbols and all(isinstance(s, str) and s.strip() for s in symbols):
            out[str(day)[:10]] = {s.strip().upper() for s in symbols}
    return out


def mismatches(live_path: str | Path) -> list[tuple[str, str]]:
    """(day, symbol) of every bar the book's morning audit found different (WHICH BARS DIFFERED, the module
    docstring), in order, each once: a day THE NOTE names gives the note's symbols; any other day with a row marked
    "mismatch" gives every such row's symbol (the raw and the all row of a bar are one bar). [] when the book has
    neither table. `sqlite3.Error` when it cannot be read."""
    def read(db: sqlite3.Connection) -> list[tuple[str, str]]:
        tables = {str(row[0]) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        noted = _noted(db) if "kv" in tables else {}
        marked: dict[str, set[str]] = {}
        if "eq_bars" in tables:
            for day, symbol in db.execute("SELECT DISTINCT day, symbol FROM eq_bars WHERE audit=?",
                                          (MISMATCH,)).fetchall():
                marked.setdefault(str(day)[:10], set()).add(str(symbol).strip().upper())
        return sorted((day, symbol) for day, symbols in {**marked, **noted}.items() for symbol in symbols)

    return guard.read(live_path, read)


def mark(db: sqlite3.Connection, bars: list[tuple[str, str]], *, now: float) -> int:
    """THE AUDIT MARKS (the module docstring) for the mismatched `bars` ((day, symbol) pairs): how many
    `audit_mismatch` events were written (a (pid, day) already marked writes nothing)."""
    if not bars:
        return 0
    holders: dict[str, list[forward_db.Program]] = {}
    for program in forward_db.programs(db, active=False, code=False):    # a listing: the marks read NEEDS, no text
        if program.lane == "control" or program.reason == "control":
            continue
        needs = program.needs if isinstance(program.needs, Mapping) else {}
        for symbol in needs.get("symbols") or ():
            holders.setdefault(str(symbol).strip().upper(), []).append(program)
    written = 0
    for day, symbol in bars:
        try:
            when = dt.date.fromisoformat(day)
        except ValueError:
            continue
        for program in holders.get(symbol, ()):
            if program.first_day > when:
                continue
            seq = forward_db.event(db, "audit_mismatch", pid=program.pid, day=day, at=now, once="audit",
                                   payload={"why": "the book's morning re-fetch found a bar of this day different "
                                                   "from the one a decision used: the day leaves the counted days",
                                            "symbol": symbol})
            written += 1 if seq else 0
    if db.in_transaction:
        db.commit()
    return written


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py): skipped when `forward_db.mode` is "off" or the forward store is absent; else
    the audit marks and the chain check (the module docstring). The receipt: {"marked" (events written), "chain_ok",
    "rows", "head"}; with no live book the marks are skipped and the chain is still checked.

    Also "marks": "ok" | "no book" | "unread", and "mismatched" (the book's mismatched bars read this morning)."""
    from ..swarm import settings as swarm_settings

    root = Path(ctx.root)
    settings = swarm_settings.load(root, config=getattr(ctx, "config", None))
    try:
        mode = forward_db.mode(settings)
    except NotImplementedError:  # a release without the forward store's package: nothing to mark, never a crash
        return {"status": "skipped", "why": "the forward store is not in this release (league/ops/forward_db.py)"}
    if mode == "off":
        return {"status": "skipped", "why": "elane.forward.mode is off"}
    if not (root / forward_db.DB).exists():
        return {"status": "skipped", "why": "no forward store yet"}
    now = float(ctx.now())
    db = forward_db.open_db(root)
    try:
        marked, marks, bars = 0, "no book", []
        if (root / LIVE_DB).exists():
            try:
                bars = mismatches(root / LIVE_DB)
                marks = "ok"
            except sqlite3.Error as exc:
                marks = "unread"
                ctx.alert("warning", f"forward_audit: the live book's bars audit could not be read "
                                     f"({type(exc).__name__}): no forward day was marked this morning")
            marked = mark(db, bars, now=now)
            try:    # RELEASE E4 (package J): a live panel decision whose morning re-read was a mismatch
                from . import forward_xs

                marked += forward_xs.audit_marks(db, root / LIVE_DB, now=now)
            except sqlite3.Error as exc:
                marks = "unread"
                ctx.alert("warning", f"forward_audit: the live book's panel decisions could not be read "
                                     f"({type(exc).__name__}): no panel forward day was marked this morning")
        chain = forward_db.verify_chain(db)
        ok = bool(chain.get("ok"))
        rows, head, first_bad = chain.get("rows"), chain.get("head"), chain.get("first_bad")
        forward_db.event(db, "chain_ok" if ok else "chain_broken", at=now,
                         payload={"why": "the registry's hash chain holds" if ok else
                                         "a registry row does not hold its hash: stop the forward jobs and compare "
                                         "with the backup", "rows": rows, "head": head, "first_bad": first_bad})
        if db.in_transaction:
            db.commit()
        if not ok:
            ctx.alert("warning", f"forward_audit: the forward registry's hash chain is broken at pid {first_bad} "
                                 f"({rows} rows): stop the forward jobs and compare the forward store with the backup")
        return {"marked": marked, "marks": marks, "mismatched": len(bars), "chain_ok": ok, "rows": rows, "head": head}
    finally:
        db.close()


__all__ = ["LIVE_DB", "MISMATCH", "NOTE_KEY", "mismatches", "mark", "run"]
