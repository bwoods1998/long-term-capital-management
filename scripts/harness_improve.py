#!/usr/bin/env python3
"""Operate the persistent, no-provider-call harness lab. See playbooks/harness-improvement.md.

The scheduler lane: capture, prepare, stage, evaluate, reconcile, watch. The research, memory, data and execution lanes
(`league/swarm/harness_lanes.py`), one command per step: `measure` (read-only, on the House) -> `rank` -> `prepare` ->
`stage` -> `evaluate` -> deploy through the watchdog -> `canary` -> `reconcile`; `next` prints each candidate's next
command, `brief` what its patch author may see, `lanes` the predeclared definitions.
"""
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
from league.swarm import harness_lanes as lanes
from league.watchdog import tree_digest

#: Commands that never open a journal (read-only, or definitions only).
NO_JOURNAL = ("measure", "lanes")
#: The supervised observer's lane measurement: the last day, read only, at most this often (about 1.5 CPU seconds on the
#: House per measurement, Sept 30, 2026). Written to its own directory only; registering candidates stays the operator's.
LANES_EVERY = 1800
LANES_WINDOW = 86400


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, help="private, dedicated harness journal directory (every command but measure/lanes)")
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
    part.add_argument("--swarm", type=Path, help="scheduler lane (and lanes on the House): the swarm state, read only")
    part.add_argument("--deploy-base", type=Path, help="scheduler lane: directory with current and deploys.jsonl")
    part.add_argument("--measurement", type=Path, help="a lane candidate: `measure` of its registered window")
    sub.add_parser("status")
    part = sub.add_parser("measure", help="read-only lane measurement of a swarm state directory (run it on the House)")
    part.add_argument("--swarm", type=Path, required=True)
    part.add_argument("--seconds", type=int, default=6 * 3600)
    part.add_argument("--since", type=float, help="window start (epoch seconds); with --until instead of --seconds")
    part.add_argument("--until", type=float, help="window end (epoch seconds; default now)")
    part.add_argument("--lanes", help="comma-separated lanes (default: all)")
    part.add_argument("--examples", type=int, default=40, help="retained disqualified results to read for signatures")
    part.add_argument("--out", type=Path, help="write the document here (mode 0600) and print its summary")
    sub.add_parser("lanes", help="print the lanes' predeclared definitions")
    part = sub.add_parser("rank", help="register lane bottlenecks over their thresholds and print them ranked")
    part.add_argument("--base", required=True, help="full Git SHA of the measured running release")
    source = part.add_mutually_exclusive_group(required=True)
    source.add_argument("--measurement", type=Path, help="a `measure` document")
    source.add_argument("--swarm", type=Path, help="measure this state directory now (read only)")
    part.add_argument("--seconds", type=int, default=6 * 3600)
    part.add_argument("--out", type=Path, help="also write the ranked list here (mode 0600)")
    part = sub.add_parser("brief", help="what a lane candidate's patch author may see")
    part.add_argument("key")
    part = sub.add_parser("canary", help="start a promoted lane candidate's canary, or flip its gate by hand")
    part.add_argument("key")
    part.add_argument("--measurement", type=Path, help="`measure` taken after the watchdog promoted the evaluated tree")
    part.add_argument("--fraction", type=float, help="share of units in the canary arm (default: the lane's)")
    flip = part.add_mutually_exclusive_group()
    flip.add_argument("--revert", action="store_true", help="flip the gate to the old behavior now")
    flip.add_argument("--retain", action="store_true", help="keep the new behavior for every unit (operator decision)")
    sub.add_parser("next", help="each lane candidate's next command")
    return p


def load_json(path: Path) -> dict:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ImprovementError(f"{path} is not a JSON object")
    return value


def write_private(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".{os.getpid()}.part")
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, indent=1, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(part, path)


def measure(args) -> dict:
    wanted = [x for x in (args.lanes or "").split(",") if x] or None
    for name in wanted or []:
        if name not in lanes.LANES:
            raise ImprovementError(f"no lane {name!r}: {sorted(lanes.LANES)}")
    now = args.until if args.until is not None else time.time()
    doc = lanes.measure(args.swarm, now=now, since=args.since, seconds=args.seconds, lanes=wanted, examples=args.examples)
    if args.out:
        write_private(args.out, doc)
        return {"written": str(args.out), "window": doc["window"], "errors": doc["errors"],
                "metrics": {k: {m: v for m, v in lane["metrics"].items() if m != "tallies"} for k, lane in doc["lanes"].items()}}
    return doc


def reconcile(lab, args, key):
    job = lab.worklist.get(key)
    if job is not None and job.details.get("lane") and getattr(args, "measurement", None):
        return lab.reconcile_lane(key, measurement=load_json(args.measurement))
    if args.swarm is None or args.deploy_base is None:
        raise ImprovementError("reconcile needs --measurement (a lane candidate) or --swarm and --deploy-base")
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
    if args.command == "rank":
        doc = load_json(args.measurement) if args.measurement else lanes.measure(args.swarm, seconds=args.seconds)
        ranked = lab.capture_lanes(doc, base=args.base)
        out = {"window": doc.get("window"), "source": {k: (doc.get("source") or {}).get(k) for k in ("release", "digest")},
               "policy": lanes.POLICY, "candidates": ranked}
        if args.out:
            write_private(args.out, out)
        return out
    if args.command == "brief":
        return lab.brief(args.key)
    if args.command == "canary":
        if args.revert or args.retain:
            return lab.canary_stop(args.key, state="retained" if args.retain else "reverted")
        if not args.measurement:
            raise ImprovementError("canary needs --measurement (or --revert / --retain)")
        return lab.canary_start(args.key, measurement=load_json(args.measurement), fraction=args.fraction)
    if args.command == "next":
        return {"next": lab.next_steps(root=str(args.root), repo=str(args.repo))}
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


def lanes_snapshot(root: Path, swarm: Path, *, now: float | None = None) -> dict:
    """The observer's bottleneck capture for the lanes: measure the last day read-only and write the measurement and its
    ranked bottlenecks to the observer's own directory (`lanes-measurement.json`, `lanes-ranked.json`, mode 0600). The
    operator copies them out and registers candidates with `rank --measurement`; nothing here opens the journal."""
    doc = lanes.measure(swarm, now=now, seconds=LANES_WINDOW, examples=20)
    ranked = lanes.rank(doc)
    write_private(root / "lanes-measurement.json", doc)
    write_private(root / "lanes-ranked.json", {"at": doc["until"], "window": doc["window"], "policy": lanes.POLICY,
                                               "source": {k: (doc.get("source") or {}).get(k) for k in ("release", "digest")},
                                               "candidates": ranked})
    return {"lanes_at": doc["until"], "lanes_captured": sum(1 for r in ranked if r["captured"]),
            "lanes_errors": sorted(doc["errors"])}


def heartbeat(args, identity, result):
    failures = [str(row['error'])[:160] for row in (result.get('reconciliation') or {}).values()
                if isinstance(row, dict) and row.get('error')]
    parts = [str(result['error'])[:200]] if result.get('error') else []
    if failures:
        parts.append(f"{len(failures)} reconciliation error(s): " + '; '.join(failures[:2]))
    write_json(args.root / "observer-heartbeat.json", {**identity, "at": time.time(),
        "error": '; '.join(parts)[:512] or None, "reconciliation_error_count": len(failures),
        "waiting": result.get("waiting"), **(result.get("lanes") or {})})


def main() -> int:
    args = parser().parse_args()
    if args.command in NO_JOURNAL:
        try:
            result = measure(args) if args.command == "measure" else {"policy": lanes.POLICY, "lanes": {
                name: {**lane.spec(), "lane_sha": lanes.lane_sha(lane)} for name, lane in lanes.LANES.items()}}
        except (ValueError, OSError, sqlite3.Error) as exc:
            result = {"error": str(exc)}
        print(json.dumps(result, sort_keys=True, default=str), flush=True)
        return 1 if "error" in result else 0
    if args.root is None:
        print(json.dumps({"error": "--root (the private harness journal) is required for this command"}), flush=True)
        return 1
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
            lanes_last, lanes_state = 0.0, {}
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
                if time.time() - lanes_last >= LANES_EVERY:
                    lanes_last = time.time()
                    try:
                        lanes_state = lanes_snapshot(args.root, args.swarm)
                    except (ValueError, OSError, sqlite3.Error) as exc:
                        lanes_state = {"lanes_error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                result["lanes"] = lanes_state
                heartbeat(args, identity, result)
                time.sleep(max(30, min(60, args.interval)))
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
