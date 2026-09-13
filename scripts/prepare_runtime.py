#!/usr/bin/env python3
"""Freeze a private research configuration. No network or model requests."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_runtime.credentials import load_api_key
from portfolio_runtime.evidence import save

ROOT = Path(__file__).resolve().parents[1]


def prepare(directory, *, hours=5, budget="90", start_in_minutes=0, with_forks=False):
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Choose an empty run directory; existing runs are immutable")
    amount = Decimal(budget)
    if (
        not amount.is_finite()
        or not 0 < amount <= 90
        or not 0.1 <= hours <= 8
        or not 0 <= start_in_minutes <= 120
    ):
        raise ValueError("Invalid bounded run envelope")
    if with_forks and (amount <= 4 or hours < 1):
        raise ValueError("Fork experiment requires more than $4 and at least one hour")
    path = ROOT / "data/sp500-evidence.json"
    raw = path.read_bytes()
    evidence = json.loads(raw)
    if len(evidence["companies"]) < 490:
        raise ValueError("Full-universe evidence has not been captured")
    now = time.time()
    start = int(now + start_in_minutes * 60)
    if (
        datetime.fromisoformat(
            evidence["universe"]["expires_at"].replace("Z", "+00:00")
        ).timestamp()
        < start + hours * 3600
    ):
        raise ValueError("Membership snapshot will expire during this run")
    directory.mkdir(parents=True, mode=0o700)
    anchor = ROOT / ".data/runtime/account-anchor.json"
    created = (
        json.loads(anchor.read_text())["created_at"]
        if anchor.exists()
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    config = {
        "schema_version": 1,
        "run_id": "sp500-" + uuid.uuid4().hex[:16],
        "account_created_at": created,
        "state_dir": str(directory / "state"),
        "evidence_path": str(path),
        "evidence_sha256": hashlib.sha256(raw).hexdigest(),
        "started_epoch": start,
        "ends_epoch": start + int(hours * 3600),
        "drain_seconds": 300,
        "inference_budget_usd": str(amount),
        "cloud_budget_usd": "3.5",
        "fetch_filings": True,
        "key_fingerprint": hashlib.sha256(load_api_key().encode()).hexdigest(),
        "injected_auth": False,
        "max_concurrency": 32,
        "wave_seconds": 300,
        "min_wave_seconds": 120,
        "wave_size": 24,
    }
    if with_forks:
        config["branch_allocations"] = [
            {"id": "fork-context", "reserved_usd": "2"},
            {"id": "fork-fresh", "reserved_usd": "2"},
        ]
    save(directory / "run.json", config)
    save(
        directory / "plan.json",
        {
            "schema_version": 1,
            "run_id": config["run_id"],
            "hours": hours,
            "inference_ceiling_usd": str(amount),
            "cloud_ceiling_usd": "3.5",
            "objective": "Maintain and challenge an S&P 500 paper portfolio using persistent Sail research.",
            "source_companies": len(evidence["companies"]),
            "fork_inference_reserved_usd": "4" if with_forks else "0",
            "products": [
                "Responses API",
                "ASAP / Balanced / Flex",
                "ordinary cache / Supercache",
                "Sailboxes",
                "credential injection",
                "sleep / process recovery",
                "Voyages",
                "Usage API",
            ]
            + (["checkpoint forks"] if with_forks else []),
            "checks": [
                "Broad constituent research followed by evidence-driven questions.",
                "Fresh-context reviews paired with persistent memory.",
                "Identical-task completion-window comparisons.",
                "Source-checked allocations independently reviewed by Kimi K3.",
                "Progressive 1/4/8/16/24/32 concurrency and exact request recovery.",
                "No live trades; next-session paper fills only.",
            ],
            "stop_rule": "Five-hour deadline, not finite task completion. Budget is a ceiling, not a spending target.",
        },
    )
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=str(ROOT / ".data/runtime/five-hour"))
    parser.add_argument("--hours", type=float, default=5)
    parser.add_argument("--budget", default="90")
    parser.add_argument("--start-in-minutes", type=int, default=0)
    parser.add_argument("--with-forks", action="store_true")
    args = parser.parse_args()
    config = prepare(
        args.directory,
        hours=args.hours,
        budget=args.budget,
        start_in_minutes=args.start_in_minutes,
        with_forks=args.with_forks,
    )
    print(
        json.dumps(
            {
                "run_id": config["run_id"],
                "config": str(Path(args.directory) / "run.json"),
                "inference_ceiling_usd": config["inference_budget_usd"],
                "network_requests": 0,
            }
        )
    )
