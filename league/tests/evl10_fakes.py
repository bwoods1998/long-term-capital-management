"""Test helpers for PREREG-EVL-10 (release 1019n-r2): the registries WITHOUT READER-2's four rows, for the tests of
mechanisms written before the captain's A144 pinned league/events/programs.py `REGISTERED_AT_10`
(2026-10-23T07:10:45Z).

Pinned, EVL-R2-ON, EVL-R2-ON-SET, REC-R2-ON-PASS and REC-R2-ON-AVOID are in PROGRAMS, BY_KEY and SEATING (after every
earlier file's row AND after R3's births), EVL-R2-ON is a PREREG-EVL-6 version (its 0.13 in the screen's own count,
`budget6`), league/events/births.py `RESERVED` releases the 0.13 it held for this file, and the decision scheduler has
a live part (`decide-close-r2:<D>`). The earlier releases' tests of that machinery (the births' budget and order, the
screen's count, the report, the site, the tables' order) were written on the registries as they stood before, and every
one of them ran so until this pin. `unpinned_10` runs such a test on those registries exactly (REGISTERED_AT_10 None,
`programs.refresh_7`), as league/tests/evl7_fakes.py `unpinned_7` runs PREREG-EVL-7's predecessors' tests. A module
whose tests are all of that kind imports `setUpModule` and `tearDownModule` from here; a class can take `off_10`.

THE ROWS' OWN EFFECTS ON THOSE PATHS, and THE PROOF that every earlier program's shadow intents and real-money picks are
the same with and without them, are league/tests/test_events_evl10.py's, on the registries as pinned; the rest of the
suite runs pinned, as the House does.
"""

from __future__ import annotations

import contextlib
import functools
from typing import Any, Iterator
from unittest import mock

from league.events import programs as P


@contextlib.contextmanager
def unpinned_10() -> Iterator[None]:
    """The registries without READER-2's rows for the block (REGISTERED_AT_10 None, rebuilt by `refresh_7`), restored
    and rebuilt on exit."""
    patch = mock.patch.object(P, "REGISTERED_AT_10", None)
    patch.start()
    P.refresh_7()
    try:
        yield
    finally:
        patch.stop()
        P.refresh_7()


def off_10(cls: type) -> type:
    """A TestCase class decorator: every test of the class (its setUp included) runs without READER-2's rows."""
    original = cls.setUp

    @functools.wraps(original)
    def setUp(self: Any) -> None:  # noqa: N802 - unittest's name
        ctx = unpinned_10()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        original(self)
    cls.setUp = setUp
    return cls


_HELD: list[contextlib.AbstractContextManager] = []


def setUpModule() -> None:  # noqa: N802 - unittest's name
    """A module's tests without READER-2's rows (the module imports this and `tearDownModule`)."""
    ctx = unpinned_10()
    ctx.__enter__()
    _HELD.append(ctx)


def tearDownModule() -> None:  # noqa: N802 - unittest's name
    while _HELD:
        _HELD.pop().__exit__(None, None, None)


__all__ = ["unpinned_10", "off_10", "setUpModule", "tearDownModule"]
