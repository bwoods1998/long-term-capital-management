"""The decider's kind table: a request kind -> the module the isolated child runs it with (A8.8).

Owner: hooks. `league/live/decider.py` imports THIS module only (never another of league.equity): its child answers a
("kind", <kind>, <op>, <payload>) message by `module_for(kind).handle(op, payload, state)`, with the same isolation as
an options decision (uid 65534, its own network namespace, rlimits, an empty environment). A later equity kind is a row
here and a module beside it: no league/live edit, so the options execution fingerprint does not move for it.
"""

from __future__ import annotations

from types import ModuleType

#: kind -> the importable module whose `handle(op, payload, state) -> dict` the child calls.
KINDS: dict[str, str] = {"equity": "league.equity.child"}


def module_for(kind: str) -> ModuleType:
    """The module of `kind` (imported once per child); ValueError for a kind not in `KINDS`."""
    raise NotImplementedError("hooks: league/equity/kinds.py module_for")


__all__ = ["KINDS", "module_for"]
