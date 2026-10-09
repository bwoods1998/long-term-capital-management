"""Money tables for the tests (release L-D, Oct 9, 2026).

Release L-D moved three rows of the constitution's `options_money.probe`: `loss_basis` "gross" -> "net", `max_open` 3 -> 8
and `demotion` "dm0" -> "dm1". Their values before it are fast lane v2's, and setting them back is the CON-only rollback
(docs/operations.md, **Release L-D**). The tests of fast lane v2's rules (the gross budget, three Probe slots, D5 and the
forward-negative demotion) run on `rollback_table()`, so they pin the rollback path to what fast lane v2 did; the tests
of L-D's rules run on the constitution in force.
"""

from __future__ import annotations

import copy
from typing import Any

from league.constitution import CONSTITUTION

#: The three rows release L-D moved, at fast lane v2's values (the CON-only rollback).
FAST_LANE_V2 = {"loss_basis": "gross", "max_open": 3, "demotion": "dm0"}


def constitution(**probe: Any) -> dict:
    """A copy of the constitution with `probe`'s rows set in `options_money.probe`."""
    c = copy.deepcopy(CONSTITUTION)
    c["options_money"]["probe"].update(probe)
    return c


def table(**probe: Any):
    """The money table of `constitution(**probe)`."""
    from league.live import money as M

    return M.Table.from_constitution(constitution(**probe))


def rollback_table(**probe: Any):
    """The CON-only rollback's money table: fast lane v2's three rows (`FAST_LANE_V2`), with `probe` on top."""
    return table(**{**FAST_LANE_V2, **probe})
