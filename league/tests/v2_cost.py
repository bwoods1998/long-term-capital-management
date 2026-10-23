"""Test helpers for THE OWNER'S GOAL V3'S COMPUTE LINE (release 1019m-cost, the captain's A145): THE COST RULE's figures AS
BUDGET RULE 3 LEFT THEM, for the tests of mechanisms written under goal V2's $5 a day, never above $25.

Goal V3 (04:40Z Oct 23, 2026), item 5: "Cost: metered compute <= $10 a day plus half the trailing week's realized net
profit, never above $50". Release 1019m-cost moved league/ops/budget.py `BASE_USD_DAY` 5 -> 10, `CEILING_USD_DAY`
25 -> 50 and the lane's part `LANE_USD_DAY` 3 -> 6 (RULE_VERSION 4), and the lane's own line, league/config.json
`events.verdict_usd_day` and its default league/events/house.py `VERDICT_USD_DAY`, 3 -> 6. The earlier releases' tests
of the runway, the day's figure, the overlay's knobs, the gate's holds, the lane's line, the meters and the reports were
written with rule 3's figures in their fixtures ("the $25 ceiling's Sail 20", "the floor's $0.34 of research", "the
lane's $3"). `v2_cost` runs such a test on rule 3's figures exactly: the three constants and the House's default set
back. `RULE_VERSION` and `SCHEMA` stay the code's (they name the file the code writes and reads, not a figure). The
mechanisms those tests hold are the same code; THE V3 FIGURES' OWN EFFECTS are tested on the figures in force
(league/tests/test_ops_budget.py `CostRule`, `LaneAllowance`, `test_another_rules_file_is_no_file`, and the tests that
name goal V3).
"""
from __future__ import annotations

import contextlib
import functools
import inspect
from typing import Any, Iterator
from unittest import mock

from league.ops import budget as B

#: Budget rule 3's figures (the goal of Oct 19, 2026, item 4), as release 1019l ran them.
RULE3 = {"BASE_USD_DAY": 5.0, "CEILING_USD_DAY": 25.0, "LANE_USD_DAY": 3.0}
#: The lane's own line under rule 3 (league/config.json `events.verdict_usd_day`, league/events/house.py's default).
VERDICT_USD_DAY_RULE3 = 3.0


@contextlib.contextmanager
def v2_cost() -> Iterator[None]:
    """THE COST RULE's figures and the House's default lane line as budget rule 3 left them, for the block. The House's
    lane module is imported here, not at this module's import, and only where it loads: an isolated evaluation runs the
    tests that use this with no home directory, where league/events/gw.py cannot load (and nothing then reads its
    default)."""
    patches = [mock.patch.object(B, name, value) for name, value in RULE3.items()]
    try:
        from league.events import house as H
    except Exception:  # noqa: BLE001 - the lane's module cannot load here: no test in the block reads its default
        H = None
    if H is not None:
        patches.append(mock.patch.object(H, "VERDICT_USD_DAY", VERDICT_USD_DAY_RULE3))
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()


def on_v2_cost(target: Any) -> Any:
    """A decorator: a TestCase class (every test of it, its setUp included) or one test method runs on rule 3's figures."""
    if inspect.isclass(target):
        original = target.setUp

        @functools.wraps(original)
        def setUp(self: Any) -> None:  # noqa: N802 - unittest's name
            ctx = v2_cost()
            ctx.__enter__()
            self.addCleanup(ctx.__exit__, None, None, None)
            original(self)
        target.setUp = setUp
        return target

    @functools.wraps(target)
    def run(*args: Any, **kwargs: Any) -> Any:
        with v2_cost():
            return target(*args, **kwargs)
    return run


__all__ = ["v2_cost", "on_v2_cost", "RULE3", "VERDICT_USD_DAY_RULE3"]
