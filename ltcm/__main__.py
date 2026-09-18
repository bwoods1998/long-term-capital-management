"""Command line for the Long Term Capital Management floor.

    python3 -m ltcm init                     prepare .data/ltcm and check the roster
    python3 -m ltcm run [--once]             the always-on loop
    python3 -m ltcm status                   the health projection, as JSON
    python3 -m ltcm verify                   re-hash the whole event chain
    python3 -m ltcm desks                    the roster with mode, capital and gates
    python3 -m ltcm report [--days 7]        results per desk, family and model profile
    python3 -m ltcm session <desk> [--trigger manual]
    python3 -m ltcm kill | unkill            the switch the risk engine reads first
    python3 -m ltcm publish --dry-run        what would be sent, and to where

Nothing here prints a credential, and `publish --dry-run` never opens a socket.
"""

from __future__ import annotations

import argparse
import json
import re
import os
import sys
from pathlib import Path
from typing import Any

from .analytics import ResultsLedger, markdown as render_report
from .events import ChainBroken
from .manifest import ManifestError
from .service import Service, default_config

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The desk runtime's trigger grammar, checked here so a typo fails before a session starts.
TRIGGER = re.compile(r"^[a-z][a-z0-9_:.\-]{0,48}$")


def _dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _service(args: argparse.Namespace) -> Service:
    config = default_config()
    if args.config:
        config.update(json.loads(Path(args.config).read_text(encoding="utf-8")))
    if getattr(args, "no_publish", False):
        config["publish"] = False
    return Service(args.root, config)


def cmd_init(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        report = {
            "root": str(service.root),
            "capital_dir": str(service.capital_dir),
            "events": str(service.log.path),
            "desks": sorted(service.manifests),
            "shadow_books": sorted(service.shadow_books),
            "venues": sorted(service.brokers),
            "playbooks": str(service.playbooks_dir),
            "kill_switch": str(service.kill_switch_path),
            "provider": service.provider is not None,
            "publisher": service.publisher is not None,
        }
        service.health()
        print(_dumps(report))
        return 0
    finally:
        service.close()


def cmd_run(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        result = service.run(once=args.once)
        if args.once:
            print(_dumps(result))
        return 0
    finally:
        service.close()
        if not args.once and os.environ.get("LTCM_SLOW_EXIT") != "1":
            # Sept 18, 2026: the interpreter's exit joined every thread-pool worker (the
            # Foundry's backtests run for up to 25 minutes) and every restart stalled for as
            # long. The health file and the tape are written; the supervisor restarts the loop.
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)


def cmd_status(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        print(_dumps(service.status()))
        return 0
    finally:
        service.close()


def cmd_verify(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        checked = service.log.verify()
        print(_dumps({"ok": True, "events": checked, "path": str(service.log.path)}))
        return 0
    except ChainBroken as exc:
        print(_dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    finally:
        service.close()


def cmd_desks(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        rows = []
        for desk_id, manifest in sorted(service.manifests.items()):
            state = service.ledgers[desk_id].state()
            report = service.committee.gates(desk_id)
            rows.append(
                {
                    "id": desk_id,
                    "name": manifest.name,
                    "family": manifest.family,
                    "generation": manifest.generation,
                    "parent_id": manifest.parent_id,
                    "mode": report["evidence"]["mode"],
                    "status": service.desk_status(desk_id),
                    "venues": list(manifest.venues),
                    "capital_usd": str(manifest.capital_usd),
                    "equity": str(state.equity),
                    "return_pct": str(state.time_weighted_return_pct),
                    "decisions": state.decisions,
                    "days_live": state.days_live,
                    "gate": report["gate"],
                    "gate_passed": report["passed"],
                    "gate_failed": report["failed"],
                }
            )
        print(_dumps(rows))
        return 0
    finally:
        service.close()


def cmd_report(args: argparse.Namespace) -> int:
    """The lab report: what the floor earned, what it cost, and which model earned it.

    Reads the event log and nothing else, so it is safe to run against a live floor. `--write`
    saves the markdown for the owner's architecture notes; it never touches git.
    """
    if not 1 <= args.days <= 365:
        print(_dumps({"error": "--days must be between 1 and 365"}), file=sys.stderr)
        return 2
    service = _service(args)
    try:
        report = ResultsLedger(service.log, service.manifests).report(args.days)
        written = None
        if args.write:
            directory = Path(args.write)
            if not directory.is_absolute():
                directory = Path(args.root) / directory
            directory.mkdir(parents=True, exist_ok=True)
            written = directory / f"{report['generated_at'][:10]}-lab-report.md"
            written.write_text(render_report(report), encoding="utf-8")
        if args.markdown:
            print(render_report(report))
            if written is not None:
                print(f"written {written}", file=sys.stderr)
        else:
            body = dict(report)
            if written is not None:
                body["written"] = str(written)
            print(_dumps(body))
        return 0
    finally:
        service.close()


def cmd_session(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        manifest = service.manifests.get(args.desk_id)
        if manifest is None:
            print(_dumps({"error": f"unknown desk {args.desk_id}"}), file=sys.stderr)
            return 2
        if not TRIGGER.match(args.trigger):
            print(_dumps({"error": f"invalid trigger {args.trigger!r}"}), file=sys.stderr)
            return 2
        context = service.context(manifest, None)
        runner = service.desk(manifest, context)
        if runner is None:
            print(_dumps({"error": "desk runtime unavailable"}), file=sys.stderr)
            return 3
        # The desk runtime owns its session events, including `desk.session_started`.
        result = runner.run_session(args.trigger)
        print(
            _dumps(
                {
                    "session_id": getattr(result, "session_id", None),
                    "turns": getattr(result, "turns", None),
                    "requests": getattr(result, "requests", None),
                    "cost_usd": str(getattr(result, "cost_usd", "")),
                    "intents": getattr(result, "intents", None),
                    "reason": getattr(result, "reason", None),
                }
            )
        )
        return 0
    finally:
        service.close()


def cmd_kill(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        path = service.kill(args.reason)
        print(_dumps({"engaged": True, "path": str(path), "reason": args.reason}))
        return 0
    finally:
        service.close()


def cmd_promote(args: argparse.Namespace) -> int:
    """Owner decision: move one desk between shadow and live capital. Public, like every event."""
    service = _service(args)
    try:
        manifest = service.manifests.get(args.desk_id)
        if manifest is None:
            print(_dumps({"error": f"unknown desk {args.desk_id}"}))
            return 2
        if args.to == "live" and not [v for v in manifest.venues if v != "shadow"]:
            print(_dumps({"error": "desk has no live venue in its manifest"}))
            return 2
        at = service.now()
        payload = {
            "desk_id": manifest.id,
            "from": "shadow" if args.to == "live" else "live",
            "to": args.to,
            "score": {},
            "reason": f"owner decision: {args.reason}",
        }
        event = service.log.append(
            "evolution", "evolution.promoted", payload, id=f"promoted:{manifest.id}:{at[:16]}", at=at
        )
        print(_dumps({"desk_id": manifest.id, "to": args.to, "event": event.id}))
        return 0
    finally:
        service.close()


def cmd_unkill(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        released = service.unkill()
        print(_dumps({"engaged": False, "released": released}))
        return 0
    finally:
        service.close()


def cmd_publish(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        released = service.gateway.release_deferred_events()
        if args.dry_run:
            publisher = service.publisher
            state = publisher.state() if publisher is not None else {"last_seq": 0, "held": []}
            cleared = set(released)
            pending = [
                event.to_public()
                for event in service.log.read(after=int(state.get("last_seq") or 0), limit=200)
                if event.public or event.id in cleared
            ]
            print(
                _dumps(
                    {
                        "dry_run": True,
                        "site_url": service.config["site_url"],
                        "events_endpoint": "/api/capital/events",
                        "checkpoint_endpoint": "/api/capital/checkpoint",
                        "state": state,
                        "released": released,
                        "would_send": len(pending),
                        "first": pending[:3],
                        "checkpoint": json.loads(
                            json.dumps(service.checkpoint(), default=str)
                        ),
                    }
                )
            )
            return 0
        if service.publisher is None:
            print(_dumps({"error": "publishing is disabled in config"}), file=sys.stderr)
            return 2
        summary = service.publisher.push_events(released)
        service.publisher.push_checkpoint(service.checkpoint())
        print(_dumps(summary))
        return 0
    finally:
        service.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ltcm", description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    parser.add_argument("--config", default=None, help="JSON config overlay")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the data directories and report the roster")

    run = sub.add_parser("run", help="run the floor loop")
    run.add_argument("--once", action="store_true", help="one tick, then exit")
    run.add_argument("--no-publish", action="store_true", dest="no_publish")

    sub.add_parser("status", help="print the health projection")
    sub.add_parser("verify", help="re-hash the event chain")
    sub.add_parser("desks", help="print the roster")

    report = sub.add_parser("report", help="print the lab report for a trailing window")
    report.add_argument("--days", type=int, default=7, help="window length in days (default 7)")
    report.add_argument(
        "--markdown", action="store_true", help="print the markdown report instead of JSON"
    )
    report.add_argument(
        "--write",
        default=None,
        metavar="DIR",
        help="also write DIR/<date>-lab-report.md (relative to --root); never commits",
    )

    session = sub.add_parser("session", help="run one desk session now")
    session.add_argument("desk_id")
    session.add_argument("--trigger", default="manual")

    kill = sub.add_parser("kill", help="engage the kill switch")
    kill.add_argument("--reason", default="manual")
    sub.add_parser("unkill", help="release the kill switch")
    promote = sub.add_parser("promote", help="owner decision: move a desk to live or back to shadow")
    promote.add_argument("desk_id")
    promote.add_argument("--to", choices=("live", "shadow"), default="live")
    promote.add_argument("--reason", default="manual")

    publish = sub.add_parser("publish", help="push the tape and the checkpoint")
    publish.add_argument("--dry-run", action="store_true", dest="dry_run")
    return parser


COMMANDS = {
    "init": cmd_init,
    "run": cmd_run,
    "status": cmd_status,
    "verify": cmd_verify,
    "desks": cmd_desks,
    "report": cmd_report,
    "session": cmd_session,
    "kill": cmd_kill,
    "promote": cmd_promote,
    "unkill": cmd_unkill,
    "publish": cmd_publish,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "no_publish"):
        args.no_publish = False
    try:
        return COMMANDS[args.command](args)
    except (ManifestError, OSError, ValueError) as exc:
        print(_dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
