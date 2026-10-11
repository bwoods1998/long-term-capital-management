"""The `forward_audit` job: the morning marks of the forward record, and the registry's chain check (release E3).

Owner: B (league/ops/E3_INTERFACES.md). Protected. 25 minutes before each open (after the equity book's morning
re-fetch of the last decision's bars, A8.11); in a pause too. It reads the live book read-only and writes only events
of `<state>/forward.sqlite` (league/ops/forward_db.py).

- THE AUDIT MARKS: for each `eq_bars` row of the live book with `audit` "mismatch" (the re-fetch found the bar
  different from the one a decision used) and each registered program whose NEEDS hold the symbol and whose forward
  days hold the day, one `audit_mismatch` event (once a (pid, day)). A marked day leaves the program's COUNTED days
  (`forward_db.counted_days`); its row stays. A program's forward days hold a day from its `first_day` on, whether its
  row for that day is written yet or not (a program left stale that night is marked before its row comes), stopped or
  not. A CONTROL IS NEVER MARKED: it reads no bar and decides nothing. Every mismatch row the book still holds is
  read each morning, so a morning that could not read the book is made up the next.
- THE CHAIN: `forward_db.verify_chain` -> one `chain_ok` or `chain_broken` event, and for a broken chain a
  `ctx.alert("warning", ...)` (owner step: stop the forward jobs and compare with the backup). The alert's text
  holds ids, counts and dates only.

A FAILURE OF THE HOUSE NEVER MARKS A PROGRAM: a book that cannot be read marks nobody (a warning, and the receipt says
`marks` "unread"); the chain is still checked.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from . import forward_db, guard

#: The live book (league/equity/live.py: `eq_bars`), under the state root.
LIVE_DB = "live.sqlite"
#: `eq_bars.audit` of a bar the book's morning re-fetch found different.
MISMATCH = "mismatch"


def mismatches(live_path: str | Path) -> list[tuple[str, str]]:
    """(day, symbol) of every `eq_bars` row the book's morning audit marked "mismatch", in order, each once (the raw
    and the all row of a bar are one bar); [] when the book has no such table. `sqlite3.Error` when it cannot be
    read."""
    def read(db: sqlite3.Connection) -> list[tuple[str, str]]:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='eq_bars'").fetchone() is None:
            return []
        return [(str(row[0])[:10], str(row[1]).strip().upper()) for row in db.execute(
            "SELECT DISTINCT day, symbol FROM eq_bars WHERE audit=? ORDER BY day, symbol", (MISMATCH,)).fetchall()]

    return guard.read(live_path, read)


def mark(db: sqlite3.Connection, bars: list[tuple[str, str]], *, now: float) -> int:
    """THE AUDIT MARKS (the module docstring) for the mismatched `bars` ((day, symbol) pairs): how many
    `audit_mismatch` events were written (a (pid, day) already marked writes nothing)."""
    if not bars:
        return 0
    holders: dict[str, list[forward_db.Program]] = {}
    for program in forward_db.programs(db, active=False):
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
    if forward_db.mode(settings) == "off":
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


__all__ = ["LIVE_DB", "MISMATCH", "mismatches", "mark", "run"]
