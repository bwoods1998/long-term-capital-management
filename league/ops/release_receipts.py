"""RELEASE RECEIPTS (release E3, D17): a deploy's declared metric, read back by the stall job after its window.

Owner: C (league/ops/E3_INTERFACES.md). Protected. A release declares what it expects to move; the House reads the
metric back and lists the verdict. Listed, never reverted: a receipt changes no setting and rolls nothing back.

A DECLARATION is an object {"id", "release", "metric", "direction": "up" | "down", "min_delta", "window_hours",
"why"} in `<release>/docs/benchmarks/release_receipts.json` (`DECLARATIONS`: {"schema": 1, "receipts": [...]};
protected, rule-level; `window_hours` is `READ_AFTER_HOURS` when left out). `metric` is a dotted path into
`funnel.window(root, start, end)` that resolves to a number (`metric`).

THE READ (`step`, called by league/ops/stall.py `run`, which is read-only on the swarm store; the receipts live in
their own `<state>/release-receipts.sqlite`, 0600, table `l3_receipts`, append-only). `deployed_at` =
`funnel.release_start(base, <the running release's name>)` when the stall job first sees the id (that sighting's time
when the deploy record has none); the release's name is its directory's (`Path(release_dir).name`, as the scoreboard
names it). before = the metric over [deployed_at - w, deployed_at); after = over [deployed_at, deployed_at + w), read
once now >= deployed_at + w; sd = the sample sd of the metric over the four windows before `deployed_at`. Verdict
(`VERDICTS`): "moved" when (after - before) in the declared direction >= min_delta; "wrong_way" when <= -min_delta;
"flat" otherwise; "unreadable" when either is not a number. A receipt not read `UNREAD_GRACE_HOURS` after its window
closed is `unread` (alarm RR1); one read "flat" or "wrong_way" is alarm RR2 (league/ops/forward_report.py).

Standard library only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

DB = "release-receipts.sqlite"
#: Where a release declares its receipts, relative to the release directory.
DECLARATIONS = "docs/benchmarks/release_receipts.json"
#: A declaration's default window in hours.
READ_AFTER_HOURS = 72
#: A receipt still unread this many hours after its window closed is `unread`.
UNREAD_GRACE_HOURS = 24
VERDICTS = ("moved", "flat", "wrong_way", "unreadable")
DIRECTIONS = ("up", "down")
#: `l3_receipts.kind`: `value` is the metric BEFORE on "declared" and AFTER on "read".
KINDS = ("declared", "read")
APPEND_ONLY_ERROR = "release-receipts.sqlite is append-only"

#: The whole store (idempotent). Complete from step 0.
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS l3_receipts (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('declared','read')), release TEXT NOT NULL, metric TEXT NOT NULL,
  direction TEXT NOT NULL, min_delta REAL NOT NULL, window_hours REAL NOT NULL, deployed_at REAL NOT NULL,
  value REAL, sd REAL, verdict TEXT, at REAL NOT NULL, UNIQUE (id, kind));
CREATE TRIGGER IF NOT EXISTS l3_receipts_no_update BEFORE UPDATE ON l3_receipts
  BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_ERROR}'); END;
CREATE TRIGGER IF NOT EXISTS l3_receipts_no_delete BEFORE DELETE ON l3_receipts
  BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_ERROR}'); END;
"""


def declarations(release_dir: str | Path) -> list[dict[str, Any]]:
    """The declarations of `<release_dir>/docs/benchmarks/release_receipts.json`, each with its `window_hours`. A
    malformed entry is dropped and named (`step` lists it in its `errors` and never declares it). [] when the file is
    absent or unreadable."""
    raise NotImplementedError("C: league/ops/release_receipts.py declarations")


def metric(window: Mapping[str, Any], path: str) -> float | None:
    """The number at the dotted `path` of a `funnel.window` object (e.g. "forward_record.program_sessions"); None
    when the path does not resolve to a finite number (a bool is not a number)."""
    raise NotImplementedError("C: league/ops/release_receipts.py metric")


def step(root: str | Path, base: str | Path, release_dir: str | Path, *, now: float) -> dict[str, Any]:
    """D17, one pass (the module docstring): {"declared": [id] (declared in this pass), "read": [{"id", "verdict"}]
    (read in this pass), "unread": [id], "errors": [str]}. NEVER RAISES: the stall alarm goes on without it."""
    raise NotImplementedError("C: league/ops/release_receipts.py step")


def rows(root: str | Path) -> list[dict[str, Any]]:
    """Every `l3_receipts` row in seq order (read-only; [] when the store is absent)."""
    raise NotImplementedError("C: league/ops/release_receipts.py rows")


__all__ = ["DB", "DECLARATIONS", "READ_AFTER_HOURS", "UNREAD_GRACE_HOURS", "VERDICTS", "DIRECTIONS", "KINDS", "SCHEMA",
           "APPEND_ONLY_ERROR", "declarations", "metric", "step", "rows"]
