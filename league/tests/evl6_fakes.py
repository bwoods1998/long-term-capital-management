"""Test helpers for PREREG-EVL-6 (release 1019i): the program table as release 1019h had it, for the tests of mechanisms
written against release 1019h's seats.

PREREG-EVL-6 section 1.1 moves EVERY seat to a new version (version 3 of the nine, version 2 of PREREG-EVL-4's and -5's
three, version 2 of every seatable birth registered before REGISTERED_AT_6) and makes every version it supersedes a
shadow record that seats no more. The earlier releases' tests of the event lane's machinery (the book's room, sizing,
reservation and resends, the shadow's decisions, the record's finality, PREREG-EVL-3's bands on a seating version) were
written with release 1019h's seats in their fixtures (`("EVL-ERN-READ-O1", 2)` and so on). `on_1019h` runs such a test
on release 1019h's program table exactly: no PREREG-EVL-6 version, REGISTERED_AT_6 unpinned (so no version is
superseded and the births load at version 1 alone), the earlier rows' own `can_seat`. The mechanisms they test are the
same code; the tests of PREREG-EVL-6's own rules (league/tests/test_events_evl6*.py) run on the table as it is.
"""

from __future__ import annotations

import contextlib
import functools
from typing import Any, Iterator
from unittest import mock

from league.events import programs as P


def table_1019h() -> dict[str, Any]:
    """The program module's globals as release 1019h had them (every PREREG-EVL-6 row left out, and PREREG-EVL-8's,
    which no registry held then)."""
    rows = tuple(p for p in P.PREREG_PROGRAMS if p.regfile is None and not getattr(P, "is_8", lambda _: False)(p))
    return {"PROGRAMS": rows, "PREREG_PROGRAMS": rows, "BY_KEY": {(p.id, p.version): p for p in rows},
            "BY_ID": {p.id: p for p in rows if p.version == 1}, "BIRTHS": (),
            "SEATING": tuple(p for p in rows if p.seatable and p.prereg in P.SEATING_PREREGS),
            "PREREG_SEATING": tuple(p for p in rows if p.seatable and p.prereg in P.SEATING_PREREGS)}


@contextlib.contextmanager
def before_evl6() -> Iterator[None]:
    """RELEASE 1019h'S PROGRAM TABLE for the block: REGISTERED_AT_6 unpinned and no PREREG-EVL-6 row (`table_1019h`);
    the births a store holds load at version 1 alone. Restored on exit, whatever `load_births` rebound inside."""
    patch = mock.patch.multiple(P, REGISTERED_AT_6=None, **table_1019h())
    patch.start()
    try:
        yield
    finally:
        patch.stop()


def on_1019h(cls: type) -> type:
    """A TestCase class decorator: every test of the class (its setUp included) runs on release 1019h's program table
    (`before_evl6`)."""
    original = cls.setUp

    @functools.wraps(original)
    def setUp(self: Any) -> None:  # noqa: N802 - unittest's name
        patch = mock.patch.multiple(P, REGISTERED_AT_6=None, **table_1019h())
        patch.start()
        self.addCleanup(patch.stop)
        original(self)
    cls.setUp = setUp
    return cls


__all__ = ["table_1019h", "before_evl6", "on_1019h"]
