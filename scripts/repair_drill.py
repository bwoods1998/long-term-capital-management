#!/usr/bin/env python3
"""The repair loop's controlled end-to-end exercise: one clearly labeled SYNTHETIC job (Sept 22, 2026).

    cd /workspace/current && /workspace/.venv/bin/python scripts/repair_drill.py --plant     # file one drill job
    cd /workspace/current && /workspace/.venv/bin/python scripts/repair_drill.py --inspect   # its states (read-only)

`--plant` writes one request file into the House's repairs inbox (`<state>/repairs-inbox/`). It
never opens the ledger for writing: the House is the ledger's only writer, and its repair engineer
turns the request into a `repair.reported` row with `source: "synthetic"` and a key starting
`synthetic:repair-drill:` on its next step. For a drill job NO model is asked and nothing is
spent: patch 1 is written deliberately wrong (a labeled tool, `league/tools/repair_drill.py`,
whose own test fails), CI refuses it, the engineer reads CI's failure text back through the
gateway (`GET /v1/github/pr/<n>/failures`), and patch 2 is written only because that text names
the failing test. Patch 2 passes, merges through the Merton workflow, reaches the box through the
updater's canary, and the job is verified after `synthetic_observe_minutes` without recurrence.

Expected states: proposed -> admitted -> reproducing -> patching -> testing (PR 1) -> revising
-> reproducing -> patching -> testing (PR 2) -> canary -> observing -> verified. (`testing`
appears twice per patch: written, then proposed.)

Needs, on the running release: the repair engineer (Merton on, the House not paused), and the
gateway's failures read deployed. Without that read the job waits for CI's failure text for
`failure_text_wait_hours` and then stops as dormant; it never revises blind.

What the drill leaves behind: the refused first PR stays open (the gateway can open pull
requests but not close them; close it by hand), and the labeled tool and its test merge to main.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREFIX = "synthetic:repair-drill:"


def plant(state: Path, *, clock=time.time, stamp: str | None = None) -> str:
    """File the drill's request in the inbox. Returns the key the House will give its job."""
    stamp = stamp or time.strftime("%Y%m%dt%H%M%S", time.gmtime(clock()))
    inbox = Path(state) / "repairs-inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    temporary = inbox / f"drill-{stamp}.tmp"
    temporary.write_text(json.dumps({"drill": stamp}), encoding="utf-8")
    temporary.replace(inbox / f"drill-{stamp}.json")
    return PREFIX + "".join(c for c in stamp.lower() if c.isalnum())[:32]


def inspect(path: Path, key: str | None = None) -> list[dict]:
    """The drill jobs' rows, oldest first, from a read-only connection (never a write on the box)."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        found = db.execute("SELECT seq, kind, at, payload FROM ledger WHERE kind IN ('repair.reported', 'repair.status') ORDER BY seq").fetchall()
    finally:
        db.close()
    rows = []
    for seq, kind, at, payload in found:
        body = json.loads(payload)
        if not str(body.get("key") or "").startswith(key or PREFIX):
            continue
        rows.append({"seq": seq, "kind": kind, "at": at, "key": body.get("key"), "state": body.get("state", "reported"),
                     "pr": body.get("pr"), "attempt": body.get("attempt"), "note": str(body.get("note") or body.get("summary") or "")[:240]})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--plant", action="store_true", help="file one synthetic drill request in the repairs inbox")
    parser.add_argument("--inspect", action="store_true", help="print the drill jobs' states (read-only)")
    parser.add_argument("--key", default=None, help="only this drill job")
    parser.add_argument("--state", default="/workspace/state", help="the House's state directory")
    args = parser.parse_args(argv)
    state = Path(args.state)
    if args.plant:
        print("filed", plant(state), "(the House reports it on the repair engineer's next step)")
    if args.inspect or not args.plant:
        waiting = sorted(p.name for p in (state / "repairs-inbox").glob("*.json")) if (state / "repairs-inbox").is_dir() else []
        if waiting:
            print("in the inbox, not yet read by the House:", ", ".join(waiting))
        if (state / "ledger.sqlite").exists():
            for row in inspect(state / "ledger.sqlite", args.key):
                print(f"{row['at']} {row['key']} {row['state']:<10} pr={row['pr']} attempt={row['attempt']} {row['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
