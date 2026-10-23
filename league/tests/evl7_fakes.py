"""Test helpers for PREREG-EVL-7 (release 1019i): the registries WITHOUT the two learners, for the tests of mechanisms
written before A125 pinned league/events/programs.py `REGISTERED_AT_7` (2026-10-22T20:14:13Z).

Pinned, the learners EVL-LRN-O1 and EVL-LRN-ON are in PROGRAMS, BY_KEY and SEATING (after every earlier file's row,
before R3's births): the House plans their work and the night's cost basis before the screen, the book holds R3's
births behind a learner that may take a name at an auction, the lane's count holds their charges, the report and the
site list them. The earlier releases' tests of that machinery (the House's plan, the book's room, the births' budget,
the report, the site) were written on the registries as they stood before, and every one of them ran so until this
pin. `unpinned_7` runs such a test on those registries exactly (REGISTERED_AT_7 None, `programs.refresh_7`), as
league/tests/evl6_fakes.py `on_1019h` runs PREREG-EVL-6's predecessors' tests on release 1019h's table. A module whose
tests are all of that kind imports `setUpModule` and `tearDownModule` from here; a class can take `off_7`.

THE LEARNERS' OWN EFFECTS ON THOSE PATHS, and THE PROOF that every earlier program's shadow intents and real-money
picks are the same with and without them, are league/tests/test_events_evl7.py's and test_events_evl7_fix.py's, on the
registries as pinned; the rest of the suite runs pinned, as the House does.
"""

from __future__ import annotations

import contextlib
import functools
from typing import Any, Iterator
from unittest import mock

from league.events import programs as P


@contextlib.contextmanager
def unpinned_7() -> Iterator[None]:
    """The registries without the learners for the block (REGISTERED_AT_7 None, rebuilt by `refresh_7` with R3's births
    as loaded), restored and rebuilt on exit. They stood so before A125 pinned the learners, and PREREG-EVL-8's rows
    were in no registry then either (REGISTERED_AT_8 was pinned by A122's release 1019n, after it): the block holds
    REGISTERED_AT_8 None too (`refresh_7` composes `refresh_8`), so these tests run on exactly the registries they were
    written on. PREREG-EVL-8's own effects on these paths are league/tests/test_events_evl8*.py's."""
    patches = [mock.patch.object(P, "REGISTERED_AT_7", None)]
    if hasattr(P, "REGISTERED_AT_8"):
        patches.append(mock.patch.object(P, "REGISTERED_AT_8", None))
    for patch in patches:
        patch.start()
    P.refresh_7()
    try:
        yield
    finally:
        for patch in reversed(patches):
            patch.stop()
        P.refresh_7()


def off_7(cls: type) -> type:
    """A TestCase class decorator: every test of the class (its setUp included) runs without the learners."""
    original = cls.setUp

    @functools.wraps(original)
    def setUp(self: Any) -> None:  # noqa: N802 - unittest's name
        ctx = unpinned_7()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        original(self)
    cls.setUp = setUp
    return cls


_HELD: list[contextlib.AbstractContextManager] = []


def setUpModule() -> None:  # noqa: N802 - unittest's name
    """A module's tests without the learners (the module imports this and `tearDownModule`)."""
    ctx = unpinned_7()
    ctx.__enter__()
    _HELD.append(ctx)


def tearDownModule() -> None:  # noqa: N802 - unittest's name
    while _HELD:
        _HELD.pop().__exit__(None, None, None)


__all__ = ["unpinned_7", "off_7", "setUpModule", "tearDownModule"]
