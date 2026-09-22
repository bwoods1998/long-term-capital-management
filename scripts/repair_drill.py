#!/usr/bin/env python3
"""The repair loop's controlled end-to-end exercise: one clearly labeled SYNTHETIC job (Sept 22, 2026).

    cd /workspace && .venv/bin/python scripts/repair_drill.py --plant       # plant one drill job
    cd /workspace && .venv/bin/python scripts/repair_drill.py --inspect     # its states so far (read-only)

`--plant` appends one `repair.reported` row with `source: "synthetic"` and a key starting
`synthetic:repair-drill:`. The running House's repair engineer (`league/engineer.py`) picks it
up on its next step. For a synthetic drill job NO model is asked and nothing is spent: patch 1
is written deliberately wrong (a labeled tool, `league/tools/repair_drill.py`, whose own test
fails), CI refuses it, the engineer reads CI's failure text back through the gateway
(`GET /v1/github/pr/<n>/failures`), and patch 2 is written only because that text names the
failing test. Patch 2 passes, merges through the Merton workflow, reaches the box through the
updater's canary, and the job is verified after `synthetic_observe_minutes` without recurrence.

Expected states: proposed -> admitted -> reproducing -> patching -> testing (PR 1) -> revising
-> reproducing -> patching -> testing (PR 2) -> canary -> observing -> verified.

What the drill leaves behind: the refused first PR stays open (the gateway can open pull
requests but not close them; close it by hand), and the labeled tool and its test merge to main.
Needs the gateway's failures read deployed; without it the job stops, honestly, as dormant.
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


def plant(ledger, *, clock=time.time, stamp: str | None = None):
    """Append the drill's job. Returns its key."""
    from league.worklist import Worklist

    stamp = stamp or time.strftime("%Y%m%dt%H%M%S", time.gmtime(clock()))
    key = PREFIX + stamp
    Worklist(ledger, clock=clock).report(
        key=key, kind="bug_report", source="synthetic", severity="low", agents=[],
        summary="SYNTHETIC repair drill: prove patch -> CI refusal -> revision against CI's failure text -> merge -> deploy -> verified.",
        evidence=[{"seq": None, "at": "", "agent": "house", "excerpt": "Planted by scripts/repair_drill.py; not a real defect."}],
        details={"drill": stamp}, id=f"repair-drill:{stamp}")
    return key


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
    parser.add_argument("--plant", action="store_true", help="append one synthetic drill job to the ledger")
    parser.add_argument("--inspect", action="store_true", help="print the drill jobs' states (read-only)")
    parser.add_argument("--key", default=None, help="only this drill job")
    parser.add_argument("--state", default="/workspace/state", help="the House's state directory (ledger.sqlite)")
    args = parser.parse_args(argv)
    path = Path(args.state) / "ledger.sqlite"
    if args.plant:
        from league.ledger import Ledger

        ledger = Ledger(path)
        try:
            print("planted", plant(ledger))
        finally:
            ledger.close()
    if args.inspect or not args.plant:
        for row in inspect(path, args.key):
            print(f"{row['at']} {row['key']} {row['state']:<10} pr={row['pr']} attempt={row['attempt']} {row['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
