"""The decider's kind table: a request kind -> the module the isolated child runs it with (A8.8).

Owner: hooks. `league/live/decider.py` imports THIS module only (never another of league.equity): its child answers a
("kind", <kind>, <op>, <payload>) message by `module_for(kind).handle(op, payload, state)`, with the same isolation as
an options decision (uid 65534, its own network namespace, rlimits, an empty environment). A later kind is a row
here and a module beside it: no league/live edit, so the options execution fingerprint does not move for it.

THE PANEL SLOT (the captain's A13): "panel" -> `league.xs.child`, a module OUTSIDE this package. Release E4 built the
cross-sectional lane inside league/xs/ (its child serves "needs", "load", "run", "decide" and "drop"), so it landed
without an edit of league/live (the options fingerprint) and without one of league/equity's evidence modules (the
equity identity, `league.swarm.evaluator.EQUITY_EVIDENCE`). This module is plumbing: it is NOT in the equity identity,
so a row added here retires no equity lineage.

THE CHILD'S RUNTIME: on the root production House the child runs from a root-owned, read-only copy of exactly the files
it may import (`league.live.decider` `runtime_files`): the options decision's own, and `RUNTIME` here (the 4
`LEAGUE_FILES`, league/gym's modules, every module of this package and of league/xs). A kind whose module imports
anything else names it in `RUNTIME`, or the child cannot import it there (league/tests/test_equity_decider.py imports
every kind's module from such a copy).

THE PARENT SIDE (release E4): `BOOKS` names, for a kind the EquityBook does not run itself, the module the book asks
on the House's side for that kind's columns, bars, decide jobs, intents and live record (league/equity/live.py
`_adapter`; "panel" -> league/xs/book.py). It is imported by the book alone, never by the decider or its child, and
only by name from here: league/equity names no module of league/xs. `kind_of` reads a family's structure as its kind.

THE EVENT KIND (release R2; PREREG-EVL-1 section 8): `BOOKS["event"]` = `league.events.book` on the parent side, which
hands the book a passing program's real-money picks at each auction. It has NO ROW IN `KINDS` and nothing in the child's
`RUNTIME`: an event program is one of the pre-registered rules the House reads itself (league/events/programs.py), never
code a program wrote, so the decider is never asked for it (league/equity/live.py `_ensure_loaded` refuses it) and the
child's sealed runtime and its protected files are what they were. An event program is never a swarm family, so
`kind_of` gives "event" only to a structure named so.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

#: kind -> the importable module whose `handle(op, payload, state) -> dict` the child calls. "panel" is the slot of A13,
#: built by release E4 (league/xs/child.py).
KINDS: dict[str, str] = {"equity": "league.equity.child", "panel": "league.xs.child"}

#: What every kind's child may import, beside the options decision's files: a path ending in "/" is every *.py file
#: directly in that directory (documentation is never copied). Repository-relative, POSIX. The three `ltcm` files are
#: the NYSE calendar the engine's ctx reads (league/equity/store.py `nyse_sessions` imports `ltcm.data` when it runs;
#: `ltcm.data` imports `ltcm.broker`; both are standard library only): without them a Validation run or a look fails
#: in the root House's child at its first decision.
RUNTIME: tuple[str, ...] = ("league/__init__.py", "league/safety.py", "league/structure_core.py", "league/stats.py",
                            "league/gym/", "league/equity/", "league/xs/", "ltcm/__init__.py", "ltcm/broker.py",
                            "ltcm/data/__init__.py")


#: kind -> the importable module of its PARENT side (`book_for`): what the EquityBook asks for a kind that is not its
#: own. The "equity" kind has none: the book runs it itself.
BOOKS: dict[str, str] = {"panel": "league.xs.book", "event": "league.events.book"}


def book_for(kind: str) -> ModuleType | None:
    """The parent-side module of `kind` (imported once a process), or None for a kind that has none ("equity", and
    any kind `BOOKS` does not name)."""
    name = BOOKS.get(kind) if isinstance(kind, str) else None
    return importlib.import_module(name) if name is not None else None


def kind_of(structure: Any) -> str:
    """The decider kind that runs a family of `structure` (league/swarm/store.py `EQUITY_STRUCTURES`): "panel" for
    "panel", "event" for "event" (release R2: no swarm family has it; the book makes event instances itself), else
    "equity"."""
    return structure if structure in ("panel", "event") else "equity"


def module_for(kind: str) -> ModuleType:
    """The module of `kind` (imported once per child); ValueError for a kind not in `KINDS`."""
    name = KINDS.get(kind) if isinstance(kind, str) else None
    if name is None:
        raise ValueError(f"no decider kind {kind!r} (known: {', '.join(sorted(KINDS))})")
    return importlib.import_module(name)


def runtime_files(repo: str | Path) -> list[str]:
    """`RUNTIME` expanded against the checkout at `repo`: sorted repository-relative POSIX paths of existing files."""
    repo = Path(repo)
    out: set[str] = set()
    for entry in RUNTIME:
        if entry.endswith("/"):
            out.update(p.relative_to(repo).as_posix() for p in (repo / entry).glob("*.py") if p.is_file())
        elif (repo / entry).is_file():
            out.add(entry)
    return sorted(out)


__all__ = ["KINDS", "BOOKS", "RUNTIME", "module_for", "book_for", "kind_of", "runtime_files"]
