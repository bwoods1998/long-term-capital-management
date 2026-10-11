"""The `forward_audit` job: the morning marks of the forward record, and the registry's chain check (release E3).

Owner: B (league/ops/E3_INTERFACES.md). Protected. 25 minutes before each open (after the equity book's morning
re-fetch of the last decision's bars, A8.11); in a pause too. It reads the live book read-only and writes only events
of `<state>/forward.sqlite` (league/ops/forward_db.py).

- THE AUDIT MARKS: for each `eq_bars` row of the live book with `audit` "mismatch" (the re-fetch found the bar
  different from the one a decision used) and each registered program whose NEEDS hold the symbol and whose forward
  days hold the day, one `audit_mismatch` event (once a (pid, day)). A marked day leaves the program's COUNTED days
  (`forward_db.counted_days`); its row stays.
- THE CHAIN: `forward_db.verify_chain` -> one `chain_ok` or `chain_broken` event, and for a broken chain a
  `ctx.alert("warning", ...)` (owner step: stop the forward jobs and compare with the backup). The alert's text
  holds ids, counts and dates only.

Standard library only.
"""

from __future__ import annotations

from typing import Any


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py): skipped when `forward_db.mode` is "off" or the forward store is absent; else
    the audit marks and the chain check (the module docstring). The receipt: {"marked" (events written), "chain_ok",
    "rows", "head"}; with no live book the marks are skipped and the chain is still checked."""
    raise NotImplementedError("B: league/ops/forward_audit.py run")


__all__ = ["run"]
