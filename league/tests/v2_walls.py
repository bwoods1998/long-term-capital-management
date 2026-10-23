"""Test helpers for THE OWNER'S GOAL V3 (release 1019l, the captain's A138): the money table AS RELEASE 1019i LEFT IT, for
the tests of mechanisms written under the V2 goal's walls.

Goal V3 (04:40Z Oct 23, 2026) made the walls the owner's balance: release 1019l moved `equity_money.event.
position_share.learning` 0.02 -> 0.05 and `.probe` 0.035 -> 0.05, `options_money.probe.loss_budget_usd` 400 and
`.loss_total_usd` 800 -> 1900, `options_money.daily_stop_share` 0.35 -> 0.25, and league/events/done.py
`LOSS_TOTAL_USD` 800 -> 1900. The earlier releases' tests of the book's sizing, room, reservation and resends, the
loss budget's windows and refusals, the stops, the standing grant's digests and the reports were written with those
figures in their fixtures (2 shares at $20 = 2% of $2,000, "the $400 window", "the 800 stop", the 1019i pair).
`v2_walls` runs such a test on release 1019i's table exactly: the five rows and three bounds set back (league/tests/equity_design.py
`before_1019l`), release 1019n's row and bound left out (PREREG-EVL-8's PX learning room, `before_1019n`), `PINNED_DIGEST`
and `equity_design.DIGESTS` release 1019i's, `LOSS_TOTAL_USD` 800. The mechanisms
they test are the same code; THE V3 ROWS' OWN EFFECTS are league/tests/test_v3_walls.py's, on the table in force.
"""
from __future__ import annotations

import contextlib
import functools
from typing import Any, Iterator
from unittest import mock

from league import constitution as K
from league.events import done as DN
from league.tests import equity_design as X

#: Release 1019i's full digest (`PINNED_DIGEST` before release 1019l).
PINNED_1019I = "9c8b2221396c88f9ea8cb51c57f4e0060ffb07bfd859f1d945617c0f23b9412d"


@contextlib.contextmanager
def v2_walls() -> Iterator[None]:
    """The table, its pins and the Done reader's total as release 1019i left them, for the block."""
    patches: list[Any] = []
    for path, value in X.V3_ROWS_BEFORE.items():
        node: Any = K.CONSTITUTION
        for key in path[:-1]:
            node = node[key]
        patches.append(mock.patch.dict(node, {path[-1]: value}))
    for table, key, bound in ((K.EQUITY_MONEY_BOUNDS, "event.position_share.learning", ("0", "0.02")),
                              (K.OPTIONS_MONEY_BOUNDS, "probe.loss_budget_usd", ("0", "400")),
                              (K.OPTIONS_MONEY_BOUNDS, "probe.loss_total_usd", ("0", "800")),
                              (K.OPTIONS_MONEY_BOUNDS, "daily_stop_share", ("0.15", "0.35"))):
        patches.append(mock.patch.dict(table, {key: bound}))
    patches.append(mock.patch.object(K, "PINNED_DIGEST", PINNED_1019I))
    # (a test module that bound the pin by name at its import: `from league.constitution import PINNED_DIGEST`)
    import sys
    for name, module in list(sys.modules.items()):
        if name.startswith("league.tests.") and getattr(module, "PINNED_DIGEST", None) == K.PINNED_DIGEST:
            patches.append(mock.patch.object(module, "PINNED_DIGEST", PINNED_1019I))
    patches.append(mock.patch.dict(X.DIGESTS, X.DIGESTS_1019I))
    patches.append(mock.patch.object(DN, "LOSS_TOTAL_USD", 800.0))
    # (release 1019n's row, PREREG-EVL-8's PX learning room, and its bound: left out, as release 1019i had neither;
    # each dict is restored whole when its patch stops)
    event, bounds = K.CONSTITUTION["equity_money"]["event"], K.EQUITY_MONEY_BOUNDS
    patches += [mock.patch.dict(event, {}), mock.patch.dict(bounds, {})]
    for p in patches:
        p.start()
    event.pop(X.V8_SLOTS_ROW, None)
    bounds.pop("event.max_open_v8.learning", None)
    # (league/ops/dlane_report.py's two statements, written at its import from the table in force)
    from league.ops import dlane_report as R

    late = [mock.patch.object(R, "EQUITY_PANEL_NOTE", R.equity_panel_note()),
            mock.patch.object(R, "EQUITY_PROBE_NOTE", R.equity_probe_note())]
    for p in late:
        p.start()
    patches += late
    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()


def on_v2(cls: type) -> type:
    """A TestCase class decorator: every test of the class (its setUp included) runs on release 1019i's table."""
    original = cls.setUp

    @functools.wraps(original)
    def setUp(self: Any) -> None:  # noqa: N802 - unittest's name
        ctx = v2_walls()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        original(self)
    cls.setUp = setUp
    return cls


_HELD: list[contextlib.AbstractContextManager] = []


def in_force(cls: type) -> type:
    """A TestCase class decorator for a module run on release 1019i's table (`setUpModule`): every test of the class
    (its setUp included) reads THE TABLE IN FORCE (the module's walls lifted for the test and set again after it).
    Release 1019m (the independent review, A139): an invariant or a test named for the table in force never runs on the
    old one."""
    original = cls.setUp

    @functools.wraps(original)
    def setUp(self: Any) -> None:  # noqa: N802 - unittest's name
        held = len(_HELD)
        while _HELD:
            _HELD.pop().__exit__(None, None, None)

        def again() -> None:
            for _ in range(held):
                ctx = v2_walls()
                ctx.__enter__()
                _HELD.append(ctx)
        self.addCleanup(again)
        original(self)
    cls.setUp = setUp
    return cls


def setUpModule() -> None:  # noqa: N802 - unittest's name
    """A module's tests on release 1019i's table (the module imports this and `tearDownModule`)."""
    ctx = v2_walls()
    ctx.__enter__()
    _HELD.append(ctx)


def tearDownModule() -> None:  # noqa: N802 - unittest's name
    while _HELD:
        _HELD.pop().__exit__(None, None, None)


def setUpModule_7() -> None:  # noqa: N802 - unittest's name
    """Both: release 1019i's table and the registries without PREREG-EVL-7's learners (league/tests/evl7_fakes.py)."""
    from league.tests import evl7_fakes as F7

    F7.setUpModule()
    setUpModule()


def tearDownModule_7() -> None:  # noqa: N802 - unittest's name
    from league.tests import evl7_fakes as F7

    tearDownModule()
    F7.tearDownModule()


__all__ = ["v2_walls", "on_v2", "in_force", "setUpModule", "tearDownModule", "setUpModule_7", "tearDownModule_7", "PINNED_1019I"]
