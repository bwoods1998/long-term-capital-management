#!/usr/bin/env python3
"""Fit on the sealed Gym and give both images the identical private model, then checkpoint twice.

    python3 scripts/data/calibration.py --state /workspace/state/data --version full-v1

The existing Gym/gate templates must already have been built and verified. No quote or fitted
parameter is printed or saved on the controller. The model moves through Sail's private file API
from the sealed Gym to the sealed gate; neither image ever receives a credential. Images become
ready only after both carry the same model and have two one-year checkpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boxlib as bl

MODEL_PATH = "/data/calibration/fill_model.json"


def model_receipt(blob: bytes) -> dict[str, Any]:
    """Metadata only; reject corrupt/non-finite parameters before either image can use them."""
    table = json.loads(blob)
    if table.get("source") != "league.gym.calibrate":
        raise ValueError("unrecognized calibration source")
    hazard = table.get("hazard")
    if not isinstance(hazard, dict):
        raise ValueError("calibration has no hazard table")
    for key, value in hazard.items():
        if (not re.fullmatch(r"q[1-5]\|[sm]\|d[0-9]+\|k[0-9]+\|t[0-9]+", key)
                or isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError("invalid calibrated hazard")
    raw_samples = table.get("meta", {}).get("fitted_on", {})
    samples = {key: int(raw_samples[key]) for key in ("days", "prints", "single", "multi", "stock_option", "dropped")
               if key in raw_samples}
    if int(samples.get("days", 0)) < 1 or int(samples.get("prints", 0)) < 1:
        raise ValueError("calibration has no Train evidence")
    version = "fm-" + hashlib.sha256(json.dumps(hazard, sort_keys=True).encode()).hexdigest()[:16] if hazard else "natural-only"
    return {"sha256": hashlib.sha256(blob).hexdigest(), "model_version": version,
            "cells": len(hazard), "samples": samples, "fitted_at": table.get("meta", {}).get("fitted_at")}


def sealed(api: Any, box: str, kind: str) -> None:
    bl.ensure_running(api, box)
    if (api.egress(box) or {}).get("document", {}).get("no_network") is not True:
        raise RuntimeError(f"the {kind} image is not sealed")
    api.exec(box, ["test", "!", "-e", "/data/secrets"], timeout=60).check()
    check = ["test", "-f", "/data/store/GATE"] if kind == "gate" else ["test", "!", "-e", "/data/store/GATE"]
    api.exec(box, check, timeout=60).check()


def fit_on_gym(api: Any, entry: dict, *, timeout: int = 3600) -> tuple[bytes, str]:
    from league.gym.driver import GymDriver

    box = entry["box_id"]
    sealed(api, box, "gym")
    driver = GymDriver(api, box, python=bl.VENV_PY)
    code = driver.ensure_code()
    identity = hashlib.sha256((entry["checkpoints"][0] + driver.version).encode()).hexdigest()[:24]
    job = f"/data/calibration/jobs/{identity}"
    q = shlex.quote
    # A completed receipt survives a lost controller connection. flock prevents duplicate fit
    # processes if an exec stream drops while the old one is still running.
    inner = (f"cd {q(code)} && {q(bl.VENV_PY)} -m league.gym.calibrate --store /data/store "
             f"--out {q(job + '/model.json')} > {q(job + '/fit.log')} 2>&1; "
             f"status=$?; echo $status > {q(job + '/exit')}; exit $status")
    command = (f"mkdir -p {q(job)} && chmod 700 /data/calibration {q(job)} && "
               f"if [ -f {q(job + '/model.json')} ] && [ \"$(cat {q(job + '/exit')} 2>/dev/null)\" = 0 ]; then true; "
               f"else flock -n /data/calibration/fit.lock sh -c {q(inner)}; fi")
    result = api.exec(box, command, timeout=timeout)
    if not result.ok:
        raise RuntimeError(f"Train calibration did not complete on {box}; private diagnostics: {job}/fit.log")
    return api.download(box, f"{job}/model.json", timeout=600), driver.version


def prepare_pair(*, version: str, api: Any = None, existing: bool = False) -> dict[str, Any]:
    """Resumable: a partially checkpointed pair stays private and can be retried safely."""
    from images import finish
    from locking import process_lock
    from league.gym.driver import build_bundle

    api = api or bl.client()
    data_box = bl.data_box_id()
    bl.ensure_running(api, data_box)
    with process_lock(bl.STATE_DIR / "calibration.lock"), bl.RemoteLease(api, data_box) as lease:
        lease.check()
        records = bl.read_json(bl.IMAGES)
        gym = (records.get("gym") or {}).get("current")
        gate = (records.get("gate") or {}).get("current")
        if not gym or not gate or gym["box_id"] == gate["box_id"]:
            raise RuntimeError("distinct verified Gym and gate images are required")
        templates = {"gym": gym["box_id"], "gate": gate["box_id"]}
        previous = bl.read_json(bl.STATE_DIR / "calibration.json")
        _, current_code = build_bundle()
        if ((existing or previous.get("code_version") == current_code)
                and previous.get("templates") == templates and previous.get("checkpoints")
                == {"gym": gym["checkpoints"], "gate": gate["checkpoints"]}
                and all(entry.get("calibration", {}).get("sha256") == previous.get("sha256") for entry in (gym, gate))):
            return previous
        try:
            sealed(api, gym["box_id"], "gym")
            sealed(api, gate["box_id"], "gate")
            if existing:
                blob, code = api.download(gym["box_id"], MODEL_PATH, timeout=600), "operator-existing-fit"
            else:
                blob, code = fit_on_gym(api, gym)
            receipt = {**model_receipt(blob), "code_version": code, "prepared_at": bl.now(),
                       "train_checkpoint": gym["checkpoints"][0], "templates": templates}
            for kind, entry in (("gym", gym), ("gate", gate)):
                lease.check()
                sealed(api, entry["box_id"], kind)
                api.exec(entry["box_id"], ["mkdir", "-p", "/data/calibration"], timeout=60).check()
                api.exec(entry["box_id"], ["chmod", "700", "/data/calibration"], timeout=60).check()
                api.upload(entry["box_id"], MODEL_PATH, blob, mode=0o600)
                check = api.download(entry["box_id"], MODEL_PATH, timeout=600)
                if hashlib.sha256(check).hexdigest() != receipt["sha256"]:
                    raise RuntimeError("the calibration changed during its private transfer")
            checkpoints = {}
            for kind, entry in (("gym", gym), ("gate", gate)):
                source = entry.get("source_checkpoint") or entry["checkpoints"][0]
                current = finish(kind, entry["box_id"], version=version, source_checkpoint=source,
                                 api=api, lease=lease)
                checkpoints[kind] = current["checkpoints"]
                lease.check()
                updated = bl.read_json(bl.IMAGES)
                updated[kind]["current"]["calibration"] = receipt
                bl.write_json(bl.IMAGES, updated)
            receipt["checkpoints"] = checkpoints
            lease.check()
            bl.write_json(bl.STATE_DIR / "calibration.json", receipt)
            return receipt
        finally:
            for entry in (gym, gate):
                try:
                    lease.check()
                    api.sleep(entry["box_id"])
                except Exception:
                    pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--version", required=True)
    parser.add_argument("--existing", action="store_true", help="checkpoint an operator-verified fit already on the Gym")
    args = parser.parse_args(argv)
    if args.state:
        bl.configure_state(args.state)
    print(json.dumps(prepare_pair(version=args.version, existing=args.existing), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
