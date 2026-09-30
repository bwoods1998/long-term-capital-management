#!/usr/bin/env python3
"""Operate the persistent, no-provider-call harness lab. See playbooks/harness-improvement.md."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import sqlite3
import sys
import time

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from league.swarm.improvement import HarnessImprovement, ImprovementError


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True, help="private, dedicated harness journal directory")
    p.add_argument("--repo", type=Path, default=REPO, help="reviewed owner repository with baseline/candidate commits")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("capture", "watch"):
        part = sub.add_parser(name)
        part.add_argument("--swarm", type=Path, required=True, help="running swarm's state directory; read only")
        part.add_argument("--base", required=True, help="full Git SHA of the measured running release")
        part.add_argument("--seconds", type=int, default=3600)
        if name == "watch":
            part.add_argument("--deploy-base", type=Path, required=True, help="directory with current and deploys.jsonl")
            part.add_argument("--interval", type=int, default=60)
    part = sub.add_parser("prepare")
    part.add_argument("key")
    part.add_argument("--worktree", type=Path, required=True)
    part = sub.add_parser("stage")
    part.add_argument("key")
    part.add_argument("--candidate", required=True)
    part = sub.add_parser("evaluate")
    part.add_argument("key")
    part.add_argument("--python", type=Path, default=Path(sys.executable))
    part = sub.add_parser("reconcile")
    part.add_argument("key")
    part.add_argument("--swarm", type=Path, required=True)
    part.add_argument("--deploy-base", type=Path, required=True)
    sub.add_parser("status")
    return p


def reconcile(lab, args, key):
    link = args.deploy_base / "current"
    if not link.is_symlink():
        raise ImprovementError("the authoritative current-release symlink is required")
    return lab.reconcile(key, deploy_log=args.deploy_base / "deploys.jsonl", current_release=link.resolve().name, swarm=args.swarm)


def step(lab, args):
    if args.command in ("capture", "watch"):
        out = {}
        if args.command == "watch":
            out["reconciliation"] = {}
            for job in lab.worklist.queue(("canary", "observing", "verified")):
                try:
                    out["reconciliation"][job.key] = reconcile(lab, args, job.key)
                except (ValueError, OSError, sqlite3.Error) as exc:
                    out["reconciliation"][job.key] = {"error": str(exc)}
        try:
            out["candidates"] = lab.capture(args.swarm, base=args.base, seconds=args.seconds)
        except (ValueError, OSError, sqlite3.Error) as exc:
            out["error"] = str(exc)
        return out
    if args.command == "prepare":
        return lab.prepare(args.key, args.worktree)
    if args.command == "stage":
        return lab.stage(args.key, args.candidate)
    if args.command == "evaluate":
        return lab.evaluate(args.key, python=args.python)
    if args.command == "reconcile":
        return reconcile(lab, args, args.key)
    return {"verified_ledger_rows": lab.ledger.verify(), "jobs": [
        {**j.view(), "decision": j.last_status.get("decision"), "proposal": j.carry.get("_proposal")}
        for j in lab.worklist.jobs().values()]}


def main() -> int:
    args = parser().parse_args()
    args.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # One transition per journal at a time, including across CLI processes. Watch releases the lock between scans.
    try:
        while True:
            with (args.root / "controller.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                lab = HarnessImprovement(args.root, repo=args.repo)
                try:
                    result = step(lab, args)
                except (ValueError, OSError, sqlite3.Error) as exc:
                    result = {"error": str(exc)}
                finally:
                    lab.close()
            print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
            if args.command != "watch":
                return 1 if "error" in result else 0
            time.sleep(max(30, min(300, args.interval)))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
