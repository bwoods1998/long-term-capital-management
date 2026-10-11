"""The decider's kind table: a request kind -> the module the isolated child runs it with (A8.8).

Owner: hooks. `league/live/decider.py` imports THIS module only (never another of league.equity): its child answers a
("kind", <kind>, <op>, <payload>) message by `module_for(kind).handle(op, payload, state)`, with the same isolation as
an options decision (uid 65534, its own network namespace, rlimits, an empty environment). A later kind is a row
here and a module beside it: no league/live edit, so the options execution fingerprint does not move for it.

THE PANEL SLOT (the captain's A13): "panel" -> `league.xs.child`, a module OUTSIDE this package whose `handle` refuses
every op today. A later release builds the cross-sectional lane inside league/xs/, so it lands without an edit of
league/live (the options fingerprint) and without one of league/equity's evidence modules (the equity identity,
`league.swarm.evaluator.EQUITY_EVIDENCE`). This module is plumbing: it is NOT in the equity identity, so a row added
here retires no equity lineage.

THE CHILD'S RUNTIME: on the root production House the child runs from a root-owned, read-only copy of exactly the files
it may import (`league.live.decider` `runtime_files`): the options decision's own, and `RUNTIME` here (the 4
`LEAGUE_FILES`, league/gym's modules, every module of this package and of league/xs). A kind whose module imports
anything else names it in `RUNTIME`, or the child cannot import it there (league/tests/test_equity_decider.py imports
every kind's module from such a copy).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

#: kind -> the importable module whose `handle(op, payload, state) -> dict` the child calls. "panel" is a slot (A13):
#: league/xs/child.py refuses every op until the panel lane is built there.
KINDS: dict[str, str] = {"equity": "league.equity.child", "panel": "league.xs.child"}

#: What every kind's child may import, beside the options decision's files: a path ending in "/" is every *.py file
#: directly in that directory (documentation is never copied). Repository-relative, POSIX. The three `ltcm` files are
#: the NYSE calendar the engine's ctx reads (league/equity/store.py `nyse_sessions` imports `ltcm.data` when it runs;
#: `ltcm.data` imports `ltcm.broker`; both are standard library only): without them a Validation run or a look fails
#: in the root House's child at its first decision.
RUNTIME: tuple[str, ...] = ("league/__init__.py", "league/safety.py", "league/structure_core.py", "league/stats.py",
                            "league/gym/", "league/equity/", "league/xs/", "ltcm/__init__.py", "ltcm/broker.py",
                            "ltcm/data/__init__.py")


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


__all__ = ["KINDS", "RUNTIME", "module_for", "runtime_files"]
