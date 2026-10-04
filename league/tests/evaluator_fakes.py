"""Explicit current-evaluator evidence for integration fixtures; never a production admission path."""

import json

from league.gym import ENGINE_VERSION
from league.gym.experiment import CONTRACT_VERSION
from league.swarm import bands
from league.swarm.evaluator import execution_fingerprint
from league.swarm.gate import run_sha
from league.tests.swarm_fakes import result


def band_proof(version, *, bundle=None):
    bundle = bundle or bands._bundle()
    return {"engine": ENGINE_VERSION, "parameter_contract": CONTRACT_VERSION,
            "execution_sha256": execution_fingerprint(), "run_sha": run_sha(version),
            "validation_bundle": bundle, "holdout_bundle": bundle, "holdout_image": "synthetic-gate"}


def passed_look(store, fid, version):
    """The PASSED holdout look a look-earned band stands on, for a fixture that bands a family by hand (release F1,
    `bands.read`: NO BAND ROW WITHOUT ITS LOOK for the same family, version and program). The look's number."""
    return store.add_look(fid, int(version["n"]), run_sha(version), passed=True, p_value=0.001, detail={"synthetic": True})


def reviewed(sha):
    from league.gym.review_contract import review_contract

    contract = review_contract()["sha256"]
    return {"sha": sha, "verdict": "pass", "contract_sha": contract,
            "audit": {"verdict": "pass", "contract_sha": contract}}


def seed_current_run(store, fid, n, *, window="validation", trials=0):
    path = store.root / "swarm.json"
    cfg = json.loads(path.read_text()) if path.exists() else {}
    gym = cfg.setdefault("gym", {})
    gym["image_checkpoint"] = gym.get("image_checkpoint") or "synthetic-image"
    path.write_text(json.dumps(cfg))
    row = result(fid, window=window)
    row.update(gym_image=gym["image_checkpoint"], gym_bundle=bands._bundle(), trials=trials)
    row["summary"]["train_eligible"] = window == "train"
    return store.add_run(fid, n, row, window=window, stress=1.0, purpose=window)


#: `evaluator.SELECTION_KEYS` as release V3-A part 1 (main 266e6861) held them: what `adopt_as_v3a` archives and clears.
V3A_SELECTION_KEYS = (
    "best_train_version", "best_train_run", "train_candidates", "submitted_run", "submitted_note",
    "robustness", "robust_failed", "robust_why", "drift_failed", "validation_version", "validation_image",
    "validation_bundle", "validation_line", "validation_view", "validation_numbers", "typical_max_loss_usd",
    "typical_by_version", "gate_ready", "review", "gated_sha", "gate_outcome", "train_passed", "incubator_reviews",
)
V3A_HOLD_KEYS = ("extension_hold", "extension_versions", "extension_cleared", "extension_lapsed")


def adopt_as_v3a(store, expected):
    """`evaluator.adopt` as release V3-A part 1 ran it (main 266e6861, the Oct 3, 2026 08:50Z deploy): every adoption,
    a league/live-only one too, archived and cleared every alive family's selection. Its body is that release's,
    statement for statement (checked against that release's module: the same families, state, notes and events), so a
    fixture holds exactly what that release left for the one-time restoration to read; never a production path."""
    from collections.abc import Mapping

    from league.swarm import incubator
    from league.swarm.bands import LIVE_BANDS, current_banded_evaluator
    from league.swarm.evaluator import KEY, gym_changed

    expected = dict(expected)
    try:
        owed = incubator.load_owed(store.root)
    except Exception:  # noqa: BLE001
        owed = {}
    with store.atomic():
        previous = store.get(KEY)
        if previous == expected:
            return {"adopted": False, "families": 0}
        count = 0
        holds = V3A_HOLD_KEYS if gym_changed(previous, expected) else ()
        now = float(store.clock())
        for fam in store.families(alive=True):
            state = fam.get("state") or {}
            recorded = state.get("incubator_barred")
            bars = {}
            if recorded is None or isinstance(recorded, Mapping):
                new = {sha: (n, why) for (fid, sha), (n, why) in owed.items() if fid == fam["id"]}
                for sha, why in incubator.adoption_bars(state).items():
                    new.setdefault(sha, (None, why))
                bars = {sha: {"why": why, "at": now, **({"version": n} if n is not None else {})}
                        for sha, (n, why) in new.items() if sha not in (recorded or {})}

            version = store.version(fam["id"], state.get("banded_version")) if state.get("banded_version") else None
            band_current = version is not None and current_banded_evaluator(state, run_sha(version))
            if fam["band"] in LIVE_BANDS and not band_current:
                store.set_band(fam["id"], "gym", reason="execution semantics changed; fresh qualification is required")
            archived = {key: state[key] for key in (*V3A_SELECTION_KEYS, *holds) if key in state}
            archived.update({key: fam.get(key) for key in ("best_train", "best_version", "best_validation", "validated_version")})
            store.event("swarm.status", fam["id"], {"action": "evaluator_adopted", "from": previous, "to": expected,
                                                       "_previous_selection": archived,
                                                       "incubator_barred": sorted(sha[:12] for sha in bars)})
            store.update_family(fam["id"], best_train=None, best_version=None, best_validation=None,
                                validated_version=None, stall=0, since_val_revisions=0, since_val_trials=0)
            cleared = {key: None for key in (*V3A_SELECTION_KEYS, *holds)}
            if holds:
                cleared["extension_versions"] = []
            cleared.update(train_candidates=[], robustness={}, robust_failed=[], robust_why={}, drift_failed={},
                           train_passed={}, incubator_reviews={}, gate_ready=False, dormant_cycles=0,
                           evaluator_trials=int(fam.get("trials") or 0), evaluator=expected,
                           previous_evaluator_selection=archived)
            if bars:
                cleared["incubator_barred"] = {**dict(recorded or {}), **bars}
            if fam["band"] != "gym" and band_current:
                cleared.pop("typical_by_version", None)
                cleared.pop("typical_max_loss_usd", None)
            store.set_state(fam["id"], **cleared)
            store.note(fam["id"], "The evaluator changed. Historical runs, lineage trials and holdout looks remain counted. "
                       "Train selection, stress/drift checks and validation are owed under the current evaluator; "
                       "rerun a defensible prior program before submitting it. This does not grant another holdout look.")
            count += 1
        store.put(KEY, expected)
    return {"adopted": True, "families": count, "previous": previous, "current": expected}
