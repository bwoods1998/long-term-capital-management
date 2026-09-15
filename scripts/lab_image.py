#!/usr/bin/env python3
"""The lab image: one provisioned Sailbox, checkpointed, that every desk sandbox is forked from.

    python3 scripts/lab_image.py build      provision, check, checkpoint, record (a few minutes)
    python3 scripts/lab_image.py status     what the record says, and whether the checkpoint exists
    python3 scripts/lab_image.py sandboxes  the desks' sandboxes and their sleep state
    python3 scripts/lab_image.py sleep      put every desk sandbox to sleep now

The record lands in `.data/ltcm/lab_image.json`; the floor reads it to know which checkpoint
to fork. Rebuilding writes a new record; the old checkpoint expires on its own.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ltcm.sailbox import SailboxClient  # noqa: E402
from ltcm.sandbox import LabImage, SandboxManager  # noqa: E402

DATA = REPO_ROOT / ".data" / "ltcm"
RECORD = DATA / "lab_image.json"
STATE = DATA / "sandboxes.json"
TOOLBOX = DATA / "toolbox"


def cmd_build(args: argparse.Namespace) -> int:
    image = LabImage(SailboxClient(), app=args.app, repo_root=REPO_ROOT, record_path=RECORD)
    record = image.build(name=args.name)
    print(json.dumps({k: record[k] for k in ("checkpoint_id", "box_id", "built_at")}, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    image = LabImage(SailboxClient(), app=args.app, repo_root=REPO_ROOT, record_path=RECORD)
    record = image.record()
    if not record:
        print("no lab image recorded; run: python3 scripts/lab_image.py build")
        return 1
    print(json.dumps(record, indent=2))
    return 0


def cmd_sandboxes(args: argparse.Namespace) -> int:
    client = SailboxClient()
    manager = SandboxManager(client, STATE, TOOLBOX)
    boxes = manager.state().get("boxes") or {}
    if not boxes:
        print("no desk sandboxes yet")
        return 0
    for desk_id, box in sorted(boxes.items()):
        try:
            row = client.get(box)
            status = row.get("status")
        except Exception as exc:  # a listing must not stop at one dead box
            status = f"error: {type(exc).__name__}"
        print(f"{desk_id:16} {box}  {status}  used today {manager.seconds_today(desk_id)}s")
    return 0


def cmd_sleep(args: argparse.Namespace) -> int:
    manager = SandboxManager(SailboxClient(), STATE, TOOLBOX)
    print(f"told {manager.sleep_all()} sandbox(es) to sleep")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", default="ltcm")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="provision and checkpoint the lab image")
    build.add_argument("--name", default="ltcm-lab-image")
    build.set_defaults(func=cmd_build)
    sub.add_parser("status", help="show the recorded image").set_defaults(func=cmd_status)
    sub.add_parser("sandboxes", help="list the desks' sandboxes").set_defaults(func=cmd_sandboxes)
    sub.add_parser("sleep", help="sleep every desk sandbox").set_defaults(func=cmd_sleep)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
