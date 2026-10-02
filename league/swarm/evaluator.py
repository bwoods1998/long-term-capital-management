"""Adopt an evaluator without transferring old selection evidence or erasing search history.

Run identities already include the Gym bundle, but family bests/robustness used to outlive that
identity. This module scopes those materialized views too. Historical runs, trials, looks, versions,
notebooks and forward records remain untouched. A stale money band returns to the Gym for fresh
qualification; its frozen live instances retain their close path. A stale band is not entry authority.

Only a change of the Gym itself (its image or bundle, `gym_changed`) clears the research selection. A change of
league/live alone moves the execution fingerprint and leaves every Gym row current (`matches`: the same image and bundle
answer the same), so the selection those rows earned stands (Oct 1, 2026: release B's league/live-only deploy cleared
every best, robustness view and validation, and no Train best was selected for hours after it). Such an adoption still
returns a stale money band to the Gym and clears the live route's facts (`LIVE_KEYS`).
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
    # The incubator's facts (release B2, `incubator.py`): its Train and drift marks and its reviews, evaluator-bound. Its
    # bars (`incubator_barred`: a failed review or audit, the gate's or the incubator's, a refusal, a bad outcome) are
    # NOT here: an adoption keeps them, so a bar is as durable as a refusal row for its program (the owner's term: a
    # program whose review or audit failed never trades the incubator).
    "train_passed", "incubator_reviews",
)
#: THE EXTENSION HOLD's records (`researcher.extension_held`): the hold a validation on the Gym earned, the versions held
#: (`extension_versions`, which a hold the operator cleared stays in), and the last hold cleared and lapsed. They are Gym
#: evidence: an adoption that changes the Gym (`gym_changed`) archives them with the selection and clears them, so a
#: version is held again only when it meets the checks on the new Gym, even one the operator cleared, whose 2017-19
#: extension verdict is then owed again under the new Gym before the operator clears it again.
HOLD_KEYS = ("extension_hold", "extension_versions", "extension_cleared", "extension_lapsed")
#: THE LIVE ROUTE'S FACTS: what an adoption clears even when the Gym did not change (`gym_changed` false: league/live
#: alone moved the execution fingerprint). The incubator's Train and drift marks name the evaluator they were made
#: under, so the live side reads them as stale either way (`incubator.current_mark`), and its reviews read a program for
#: the live route, whose code is what changed. Every other key of SELECTION_KEYS is Gym evidence, or the gate's verdict
#: on it, that the same image and bundle answer the same (`matches`), so such an adoption keeps it, with the bests.
LIVE_KEYS = ("train_passed", "incubator_reviews")


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
    earned, and the operator's clears of them, stand, and so does the research selection they earned (`adopt`)."""
    return not isinstance(previous, Mapping) or any(previous.get(key) != expected.get(key) for key in ("image", "bundle"))


def adopt(store: Any, expected: Mapping[str, Any] | None) -> dict[str, Any]:
    """At process start, invalidate derived views once per evaluator identity before workers can select.

    A missing identity cannot authorize adoption. The transition is one transaction and is restart
    safe. New families created after the transition have no old evidence to invalidate. Two kinds:

    - THE GYM CHANGED (`gym_changed`: a new image or bundle, or no identity before). The research selection
      (`SELECTION_KEYS` and the family's bests) and the extension hold's records (`HOLD_KEYS`) are archived and
      cleared, and the idle count restarts from `evaluator_trials`, worded as the evaluator's change.
    - LEAGUE/LIVE ALONE (only the execution fingerprint moved). Every Gym row the selection rests on is still current
      (`matches`, `row_matches`: the same image and bundle answer the same), so the selection, its robustness, drift and
      validation views, the gate's verdicts and the hold's records stand, and the idle and dormancy counts go on. Only
      the live route's facts (`LIVE_KEYS`) are archived and cleared. Clearing the rest stranded release B (Oct 1, 2026):
      no family held a Train best or a robustness run hours after its league/live-only deploy.

    Both return a money band whose banded evaluator is stale to the Gym (`bands.current_banded_evaluator`). The
    incubator's marks and reviews are cleared; its bars (`incubator_barred`) are kept, like the refusal and look rows: a
    verdict against a program is final for it. So a verdict held only in what the adoption clears (the gate's `review`
    or `gate_outcome` failing a program, an incubator review failing it) or only in the gate's bars owed
    (`incubator.load_owed`: an error kept them from the store before a restart) is first recorded in `incubator_barred`,
    in the same transaction (`incubator.adoption_bars`); an `incubator_barred` that cannot be read is left alone (it
    bars every program of the family: `incubator.family_bar`).
    """
    if expected is None:
        return {"adopted": False, "families": 0, "reason": "evaluator identity unavailable"}
    from . import incubator

    expected = dict(expected)
    try:
        owed = incubator.load_owed(store.root)
    except Exception:  # noqa: BLE001 - the gate reads them again at its start and records them
        owed = {}
    with store.atomic():
        previous = store.get(KEY)
        if previous == expected:
            return {"adopted": False, "families": 0}
        count = 0
        gym = gym_changed(previous, expected)
        holds = HOLD_KEYS if gym else ()
        now = float(store.clock())
        for fam in store.families(alive=True):
            state = fam.get("state") or {}
            from .bands import LIVE_BANDS, current_banded_evaluator
            from .gate import run_sha

            # THE BARS FIRST: every verdict against a program that only what this clears holds, recorded for good.
            recorded = state.get("incubator_barred")
            bars: dict[str, Any] = {}
            if recorded is None or isinstance(recorded, Mapping):
                new = {sha: (n, why) for (fid, sha), (n, why) in owed.items() if fid == fam["id"]}
                for sha, why in incubator.adoption_bars(state).items():
                    new.setdefault(sha, (None, why))
                bars = {sha: {"why": why, "at": now, **({"version": n} if n is not None else {})}
                        for sha, (n, why) in new.items() if sha not in (recorded or {})}

            version = store.version(fam["id"], state.get("banded_version")) if state.get("banded_version") else None
            band_current = version is not None and current_banded_evaluator(state, run_sha(version))
            moved = fam["band"] in LIVE_BANDS and not band_current
            if moved:
                # The House retains frozen instances for exits. Research only selects Gym families,
                # so an old band must return there rather than become permanently unevaluable.
                store.set_band(fam["id"], "gym", reason="execution semantics changed; fresh qualification is required")
            if not gym:
                # LEAGUE/LIVE ALONE: the Gym evidence stands; only the live route's facts go (archived in the event).
                archived = {key: state[key] for key in LIVE_KEYS if key in state}
                store.event("swarm.status", fam["id"], {"action": "evaluator_adopted", "from": previous, "to": expected,
                                                           "gym_changed": False, "_previous_selection": archived,
                                                           "incubator_barred": sorted(sha[:12] for sha in bars)})
                kept: dict[str, Any] = {key: {} for key in LIVE_KEYS}
                kept["evaluator"] = expected
                if bars:
                    kept["incubator_barred"] = {**dict(recorded or {}), **bars}
                store.set_state(fam["id"], **kept)
                if moved:
                    store.note(fam["id"], "The live executor changed (league/live), so this family's money band "
                               "returned to the Gym; its frozen live instances only close. The Gym did not change: its "
                               "Train selection, stress/drift checks and validation stand. This does not grant another "
                               "holdout look.")
                count += 1
                continue
            archived = {key: state[key] for key in (*SELECTION_KEYS, *holds) if key in state}
            archived.update({key: fam.get(key) for key in ("best_train", "best_version", "best_validation", "validated_version")})
            # Banded identity remains an historical claim; bands.read separately denies entry.
            store.event("swarm.status", fam["id"], {"action": "evaluator_adopted", "from": previous, "to": expected,
                                                       "gym_changed": True, "_previous_selection": archived,
                                                       "incubator_barred": sorted(sha[:12] for sha in bars)})
            store.update_family(fam["id"], best_train=None, best_version=None, best_validation=None,
                                validated_version=None, stall=0, since_val_revisions=0, since_val_trials=0)
            cleared = {key: None for key in (*SELECTION_KEYS, *holds)}
            if holds:
                cleared["extension_versions"] = []
            # The idle count starts again from here (`researcher.idle_evaluations`), and its words say the evaluator
            # changed (`evaluator_trials`), not Train's span (`span_trials` is `migrate_objective`'s mark alone).
            cleared.update(train_candidates=[], robustness={}, robust_failed=[], robust_why={}, drift_failed={},
                           train_passed={}, incubator_reviews={}, gate_ready=False, dormant_cycles=0,
                           evaluator_trials=int(fam.get("trials") or 0), evaluator=expected,
                           previous_evaluator_selection=archived)
            if bars:
                cleared["incubator_barred"] = {**dict(recorded or {}), **bars}
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
    return {"adopted": True, "families": count, "previous": previous, "current": expected, "gym_changed": gym}


__all__ = ["KEY", "SELECTION_KEYS", "HOLD_KEYS", "LIVE_KEYS", "identity", "matches", "row_matches", "gym_changed", "adopt",
           "execution_fingerprint"]
