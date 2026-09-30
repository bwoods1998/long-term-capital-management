#!/usr/bin/env python3
"""Operate the persistent, no-provider-call harness lab. See playbooks/harness-improvement.md."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from league.swarm.improvement import HarnessImprovement, ImprovementError
from league.swarm.harness_runtime import process, write_json
from league.watchdog import tree_digest


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
        part.add_argument("--release", type=Path, default=REPO if name == "watch" else None,
                          help="bind observations to this exact running release directory")
        if name == "watch":
            part.add_argument("--deploy-base", type=Path, required=True, help="directory with current and deploys.jsonl")
            part.add_argument("--interval", type=int, default=60)
            part.add_argument("--release-digest", help="reviewed release digest, supplied by the House supervisor")
            part.add_argument("--policy-signature", help="identity of the explicit private supervisor policy")
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
            out["candidates"] = lab.capture(args.swarm, base=args.base, seconds=args.seconds, release=args.release)
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


def transition(args):
    """Watchers never wait behind long evaluations while their liveness clock runs down."""
    with (args.root / "controller.lock").open("a") as lock:
        try:
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if args.command == "watch" else 0)
            fcntl.flock(lock, flags)
        except BlockingIOError:
            return {"waiting": "another harness transition holds controller.lock"}
        lab = HarnessImprovement(args.root, repo=args.repo)
        try:
            return step(lab, args)
        except (ValueError, OSError, sqlite3.Error) as exc:
            return {"error": str(exc)}
        finally:
            lab.close()


def heartbeat(args, identity, result):
    failures = [str(row['error'])[:160] for row in (result.get('reconciliation') or {}).values()
                if isinstance(row, dict) and row.get('error')]
    parts = [str(result['error'])[:200]] if result.get('error') else []
    if failures:
        parts.append(f"{len(failures)} reconciliation error(s): " + '; '.join(failures[:2]))
    write_json(args.root / "observer-heartbeat.json", {**identity, "at": time.time(),
        "error": '; '.join(parts)[:512] or None, "reconciliation_error_count": len(failures),
        "waiting": result.get("waiting")})


def main() -> int:
    args = parser().parse_args()
    args.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A lifetime lock also covers a House crash before its child's process record is persisted.
    try:
        with ExitStack() as stack:
            if args.command == "watch":
                lock = stack.enter_context((args.root / "watch.lock").open("a"))
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    print(json.dumps({"error": "an observer already holds watch.lock"}), flush=True)
                    return 1
                found = process(os.getpid())
                if found is None:
                    raise ImprovementError("cannot establish this observer's Linux process identity")
                digest = tree_digest(args.release)[0]
                if args.release_digest and digest != args.release_digest:
                    raise ImprovementError("observer source does not match the reviewed release digest")
                identity = {"pid": os.getpid(), "start": found[1], "release": str(args.release.resolve()),
                            "base": args.base, "release_digest": digest, "policy": args.policy_signature,
                            "session_started_at": time.time()}
                heartbeat(args, identity, {"waiting": "first observation"})
            while True:
                if args.command == "watch" and any(p.exists() for p in (args.swarm / "STOP", args.swarm.parent / "STOP")):
                    return 0
                try:
                    result = transition(args)
                except (ValueError, OSError, sqlite3.Error) as exc:
                    result = {"error": str(exc)}
                print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
                if args.command != "watch":
                    return 1 if "error" in result else 0
                heartbeat(args, identity, result)
                time.sleep(max(30, min(60, args.interval)))
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
