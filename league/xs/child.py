"""The "panel" kind inside the decider's isolated child: a slot, not yet a kind that runs anything (A13).

Called only by `league/live/decider.py`'s child through `league.equity.kinds.module_for("panel")`, exactly as the
"equity" kind's module is (league/equity/child.py). The panel lane is not built: `handle` REFUSES EVERY OP, so a
request that reaches this kind loads nothing, decides nothing and runs nothing, and the House's side reads a refusal
(`Decider.kind_load` raises ProgramRefused; `Decider.kind` hands the answer back as it is). Standard library only.
"""

from __future__ import annotations

from typing import Any, Mapping

#: The ops this kind serves: none.
OPS: tuple[str, ...] = ()
REFUSAL = "the panel kind is not built (league/xs is a slot, A13): it serves no op"


def handle(op: str, payload: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """One request of the "panel" kind: refused, whatever the op ({ok: False, refused: True, error}). `payload` is never
    read and `state` never written."""
    return {"ok": False, "refused": True, "error": f"{REFUSAL} ({op!r} asked)"}


__all__ = ["OPS", "REFUSAL", "handle"]
