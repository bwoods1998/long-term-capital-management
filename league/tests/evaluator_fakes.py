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


def reviewed(sha):
    from league.swarm.gate import gate_contract as review_contract

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
