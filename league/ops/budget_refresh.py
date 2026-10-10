"""The `budget_refresh` job (Oct 10, 2026; the no-captain audit's item 2): hourly and at the House's start, THE BUDGET
RULE read again and budget.json written only when a meter is RAISED (THE TOP-UP RAISE: the owner topped it up) or gets
the day's first figure, so a top-up reaches research, the knobs and the Sail guard's caps within the hour. With no usable
budget.json (none, another rule's after a deploy, stale) it is the full `budget` job. The rule and the job are
league/ops/budget.py (`refresh`); this module only names the job's entry point for the runner (`league.ops.registry`)."""
from __future__ import annotations

from typing import Any

from . import budget


def run(ctx: Any) -> dict[str, Any]:
    return budget.refresh(ctx)


__all__ = ["run"]
