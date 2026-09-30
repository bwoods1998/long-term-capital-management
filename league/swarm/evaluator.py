"""Adopt an evaluator without transferring old selection evidence or erasing search history.

Run identities already include the Gym bundle, but family bests/robustness used to outlive that
identity. This module scopes those materialized views too. Historical runs, trials, looks, versions,
notebooks and forward records remain untouched. A stale money band returns to the Gym for fresh
qualification; its frozen live instances retain their close path. A stale band is not entry authority.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

KEY = "research_evaluator"
SELECTION_KEYS = (
    "best_train_version", "best_train_run", "train_candidates", "submitted_run", "submitted_note",
    "robustness", "robust_failed", "robust_why", "drift_failed", "validation_version", "validation_image",
    "validation_bundle", "validation_line", "validation_view", "validation_numbers", "typical_max_loss_usd",
    "typical_by_version", "gate_ready", "review", "gated_sha", "gate_outcome",
)
#: THE EXTENSION HOLD's records (`researcher.extension_held`): the hold a validation on the Gym earned, the versions held
#: (`extension_versions`, which a hold the operator cleared stays in), and the last hold cleared and lapsed. They are Gym
#: evidence: an adoption that changes the Gym (`gym_changed`) archives them with the selection and clears them, so a
#: version is held again only when it meets the checks on the new Gym, even one the operator cleared, whose 2017-19
#: extension verdict is then owed again under the new Gym before the operator clears it again.
HOLD_KEYS = ("extension_hold", "extension_versions", "extension_cleared", "extension_lapsed")


@lru_cache(maxsize=4)
def execution_fingerprint(repo: Path | None = None) -> str:
    """Bind qualification to executable semantics even when a version bump was forgotten.

    Include the complete Gym and live implementations and the Gym's shared dependencies, not
    documentation. Conservative extra invalidation on an implementation-only change is allowed;
    silently carrying a band across a changed runtime/fill/context implementation is not.
    Releases are immutable, so each process hashes them once.
    """
    from ..gym.driver import LEAGUE_FILES

    repo = repo or Path(__file__).resolve().parents[2]
    files = {repo / name for name in LEAGUE_FILES}
    for name in ("gym", "live"):
        files.update((repo / "league" / name).rglob("*.py"))
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(repo).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def identity(image: Any, bundle: Any) -> dict[str, str] | None:
    return {"image": str(image), "bundle": str(bundle), "execution": execution_fingerprint()} if image and bundle else None


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


def gym_changed(previous: Mapping[str, Any] | None, expected: Mapping[str, Any]) -> bool:
    """Whether an adoption changes the Gym itself (its image or bundle; no identity before counts as a change), not only
    the execution fingerprint. A change of league/live alone moves the fingerprint and leaves every recorded validation
    current (`matches`, `Tournament.recorded_validation`: the same image and bundle answer the same), so the holds they
    earned, and the operator's clears of them, stand."""
    return not isinstance(previous, Mapping) or any(previous.get(key) != expected.get(key) for key in ("image", "bundle"))


def adopt(store: Any, expected: Mapping[str, Any] | None) -> dict[str, Any]:
    """At process start, invalidate derived views once per image/bundle before workers can select.

    A missing identity cannot authorize adoption. The transition is one transaction and is restart
    safe. New families created after the transition have no old evidence to invalidate. The extension
    hold's records (`HOLD_KEYS`) are archived and cleared with the selection when the Gym changed
    (`gym_changed`) and kept when only the execution fingerprint moved. The idle count restarts from
    `evaluator_trials`, worded as the evaluator's change.
    """
    if expected is None:
        return {"adopted": False, "families": 0, "reason": "evaluator identity unavailable"}
    expected = dict(expected)
    with store.atomic():
        previous = store.get(KEY)
        if previous == expected:
            return {"adopted": False, "families": 0}
        count = 0
        holds = HOLD_KEYS if gym_changed(previous, expected) else ()
        for fam in store.families(alive=True):
            state = fam.get("state") or {}
            from .bands import LIVE_BANDS, current_banded_evaluator
            from .gate import run_sha

            version = store.version(fam["id"], state.get("banded_version")) if state.get("banded_version") else None
            band_current = version is not None and current_banded_evaluator(state, run_sha(version))
            if fam["band"] in LIVE_BANDS and not band_current:
                # The House retains frozen instances for exits. Research only selects Gym families,
                # so an old band must return there rather than become permanently unevaluable.
                store.set_band(fam["id"], "gym", reason="execution semantics changed; fresh qualification is required")
            archived = {key: state[key] for key in (*SELECTION_KEYS, *holds) if key in state}
            archived.update({key: fam.get(key) for key in ("best_train", "best_version", "best_validation", "validated_version")})
            # Banded identity remains an historical claim; bands.read separately denies entry.
            store.event("swarm.status", fam["id"], {"action": "evaluator_adopted", "from": previous, "to": expected,
                                                       "_previous_selection": archived})
            store.update_family(fam["id"], best_train=None, best_version=None, best_validation=None,
                                validated_version=None, stall=0, since_val_revisions=0, since_val_trials=0)
            cleared = {key: None for key in (*SELECTION_KEYS, *holds)}
            if holds:
                cleared["extension_versions"] = []
            # The idle count starts again from here (`researcher.idle_evaluations`), and its words say the evaluator
            # changed (`evaluator_trials`), not Train's span (`span_trials` is `migrate_objective`'s mark alone).
            cleared.update(train_candidates=[], robustness={}, robust_failed=[], robust_why={}, drift_failed={},
                           gate_ready=False, dormant_cycles=0, evaluator_trials=int(fam.get("trials") or 0),
                           evaluator=expected, previous_evaluator_selection=archived)
            if fam["band"] != "gym" and band_current:
                # Sizing of a genuinely unchanged, already qualified semantic engine remains
                # attached to its banded version. Changed semantics are blocked by the entry proof.
                cleared.pop("typical_by_version", None)
                cleared.pop("typical_max_loss_usd", None)
            store.set_state(fam["id"], **cleared)
            store.note(fam["id"], "The evaluator changed. Historical runs, lineage trials and holdout looks remain counted. "
                       "Train selection, stress/drift checks and validation are owed under the current evaluator; "
                       "rerun a defensible prior program before submitting it. This does not grant another holdout look.")
            count += 1
        store.put(KEY, expected)
    return {"adopted": True, "families": count, "previous": previous, "current": expected}


__all__ = ["KEY", "SELECTION_KEYS", "HOLD_KEYS", "identity", "matches", "row_matches", "gym_changed", "adopt",
           "execution_fingerprint"]
