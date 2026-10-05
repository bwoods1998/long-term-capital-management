"""Local evidence keys for durable research holds; no providers or runtime imports."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def evidence_key(store, fam: Mapping[str, Any], settings: Mapping[str, Any], *,
                 release: Any, practice: str | None = None, scan: dict[str, Any] | None = None,
                 ignore_notes: tuple[int, ...] = ()) -> str:
    """A wait changes only when the family has actionable evidence or context.

    An isolated controller supplies its admitted evaluator identity as the release
    and never reads the House's practice book. The ordinary scheduler may supply a
    material practice revision. Neither key includes time, spend, or allocation.
    ``ignore_notes`` lets a finishing cycle distinguish its own recorded notes
    from guidance that arrived while its model was working.
    """
    state, gym = fam.get("state") or {}, settings.get("gym") or {}
    notes = [note for note in store.notebook(str(fam["id"]), limit=len(ignore_notes) + 1)
             if note["seq"] not in ignore_notes]
    if scan is None:
        agenda = store.get("architect_agenda_section") or {}
    else:
        if "agenda" not in scan:
            scan["agenda"] = store.get("architect_agenda_section") or {}
        agenda = scan["agenda"]
    body = {
        "family": {key: fam.get(key) for key in ("trials", "band", "revisions", "best_version", "validated_version", "validations")},
        "state": {key: state.get(key) for key in ("gate_ready", "gate_hold", "look_inflight", "gated_sha", "rewrite_ready",
                   "extension_hold", "research_wake", "research_feedback_revision")},
        "note": notes[-1]["seq"] if notes else None,
        "agenda": agenda.get("text") if isinstance(agenda, Mapping) else agenda,
        "gym": {key: gym.get(key) for key in ("image_checkpoint", "gate_checkpoint", "train_from")},
        "release": release,
        "practice": practice,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
