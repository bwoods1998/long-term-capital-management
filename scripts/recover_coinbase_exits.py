#!/usr/bin/env python3
"""One-time owner recovery: resume exit-only crypto quotes, never re-enable failed entries.

Run on the stopped floor after deploying the fee fixes. Default is a dry run. Existing
state is backed up and only the two identified house rows may change; no broker is built.
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ltcm.strategies import StrategyStore

VERSION = "coinbase-fee-recovery-2026-09-17"
DESKS = ("hilibrand", "hilibrand-3")


def recover(root, *, apply=False):
    root = Path(root)
    path = root / ".data/ltcm/strategies.json"
    data = json.loads(path.read_text())
    desks = data["desks"]
    changed = []
    for desk in DESKS:
        rows = desks.get(desk) or {}
        row = rows.get("spot_quotes") or {}
        if row.get("recovery_version") == VERSION:
            continue
        if not row.get("house") or row.get("enabled", True) or not str(row.get("note", "")).startswith("paused Sept 17:"):
            raise ValueError(f"{desk}: exit strategy no longer matches the audited paused house row")
        row.update(enabled=True, params={**row.get("params", {}), "bid": False},
                   note="Coinbase recovery: exit-only inventory management; new bids off pending positive evidence at current account fees",
                   recovery_version=VERSION, last_published_at=None)
        entry = rows.get("hourly_reversion") or {}
        if entry.get("house") and not entry.get("enabled", True):
            entry["note"] = "Entry rule still unqualified: corrected 30-day BTC/ETH/SOL replay lost after current fees; replacement research remains active"
        changed.append(desk)
    if not apply or not changed:
        return {"apply": apply, "changed": changed}
    if not (root / "STOP").exists():
        raise RuntimeError("stop the supervised floor before migrating strategy state")
    pid_path = root / "loop.pid"
    if pid_path.exists():
        pid = int(pid_path.read_text().strip())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError("floor process still running; refuse concurrent state edit")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"strategies.before-{VERSION}-{stamp}.json")
    shutil.copy2(path, backup)
    backup.chmod(0o600)
    StrategyStore(path).write(desks)
    return {"apply": True, "changed": changed, "backup": str(backup)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(recover(args.root, apply=args.apply)))
