"""Adopt an evaluator without transferring old selection evidence or erasing search history.

Run identities already include the Gym bundle, but family bests/robustness used to outlive that
identity. This module scopes those materialized views too. Historical runs, trials, looks, versions,
notebooks, forward records and money bands remain untouched. A stale band is not entry authority.
"""

from __future__ import annotations

from typing import Any, Mapping

KEY = "research_evaluator"
SELECTION_KEYS = (
    "best_train_version", "best_train_run", "train_candidates", "submitted_run", "submitted_note",
    "robustness", "robust_failed", "robust_why", "drift_failed", "validation_version", "validation_image",
    "validation_bundle", "validation_line", "validation_view", "validation_numbers", "typical_max_loss_usd",
    "typical_by_version", "gate_ready", "review", "look_inflight",
)


def identity(image: Any, bundle: Any) -> dict[str, str] | None:
    return {"image": str(image), "bundle": str(bundle)} if image and bundle else None


def matches(result: Mapping[str, Any] | None, expected: Mapping[str, Any] | None) -> bool:
    """Identity-less test pools keep their existing contract; production always has both identifiers."""
    if expected is None:
        return True
    return (isinstance(result, Mapping) and result.get("gym_image") == expected["image"] and
            result.get("gym_bundle") == expected["bundle"])


def row_matches(store: Any, row: Mapping[str, Any] | None, expected: Mapping[str, Any] | None = None) -> bool:
    expected = expected if expected is not None else store.get(KEY)
    if expected is None:
        return True
    if row is None:
        return False
    summary = row.get("summary") or {}
    if "gym_image" in summary or "gym_bundle" in summary:
        return matches(summary, expected)
    return matches(store.run_result(str(row.get("run_id") or "")), expected)


def adopt(store: Any, expected: Mapping[str, Any] | None) -> dict[str, Any]:
    """At process start, invalidate derived views once per image/bundle before workers can select.

    A missing identity cannot authorize adoption. The transition is one transaction and is restart
    safe. New families created after the transition have no old evidence to invalidate.
    """
    if expected is None:
        return {"adopted": False, "families": 0, "reason": "evaluator identity unavailable"}
    expected = dict(expected)
    with store.atomic():
        previous = store.get(KEY)
        if previous == expected:
            return {"adopted": False, "families": 0}
        count = 0
        for fam in store.families(alive=True):
            state = fam.get("state") or {}
            archived = {key: state[key] for key in SELECTION_KEYS if key in state}
            archived.update({key: fam.get(key) for key in ("best_train", "best_version", "best_validation", "validated_version")})
            # Money bands and banded identity are historical claims, retained for exits/accounting.
            # bands.read separately denies entry unless their holdout proof names the current runtime.
            store.event("swarm.status", fam["id"], {"action": "evaluator_adopted", "from": previous, "to": expected,
                                                       "_previous_selection": archived})
            store.update_family(fam["id"], best_train=None, best_version=None, best_validation=None,
                                validated_version=None, stall=0, since_val_revisions=0, since_val_trials=0)
            cleared = {key: None for key in SELECTION_KEYS}
            cleared.update(train_candidates=[], robustness={}, robust_failed=[], robust_why={}, drift_failed={},
                           gate_ready=False, dormant_cycles=0, span_trials=int(fam.get("trials") or 0),
                           evaluator=expected, previous_evaluator_selection=archived)
            store.set_state(fam["id"], **cleared)
            store.note(fam["id"], "The evaluator changed. Historical runs, lineage trials and holdout looks remain counted. "
                       "Train selection, stress/drift checks and validation are owed under the current evaluator; "
                       "rerun a defensible prior program before submitting it. This does not grant another holdout look.")
            count += 1
        store.put(KEY, expected)
    return {"adopted": True, "families": count, "previous": previous, "current": expected}


__all__ = ["KEY", "identity", "matches", "row_matches", "adopt"]
