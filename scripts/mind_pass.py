#!/usr/bin/env python3
"""One Firm Mind pass by hand, the way the floor runs it every hour (`ltcm/mind.py`).

Run ON THE FLOOR BOX (the event log lives there) or in any checkout that holds `.data/ltcm`:

    cd /workspace && .venv/bin/python scripts/mind_pass.py --dry-run          # table + book re-scored; read-only
    cd /workspace && .venv/bin/python scripts/mind_pass.py --dry-run --ask    # also one model call; only its spend is written
    cd /workspace && .venv/bin/python scripts/mind_pass.py --apply            # a real pass: write the book, publish

`--dry-run` opens `.data/ltcm/events.sqlite` read-only, prints the aggregate table of the whole
tape (a pass shows the scientist only its older part and tests proposals on the newest) and the
rule book in `.data/ltcm/mind.json` re-scored the way a pass retains it, with the rules that would be
retired. `--ask` adds the model call (key `mind:<minute>`, budget desk `mind`) and prints every
proposed rule with its out-of-sample score and verdict, without writing rules or the log; the call's
cost is added to the book's daily spend tally, because it is money all the same (the provider also
records the request). `--apply` runs a full pass even when the tape has not moved: re-score, retire,
ask, admit, write the book and publish the `lab.hypothesis` and `lab.result`. A running floor reads
the new book on its next session. `--ask` and `--apply` take the book's lock and refuse, exit 1,
while the floor's own pass holds it. Nothing here prints a credential.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ltcm.events import Event, now_iso  # noqa: E402
from ltcm.manifest import load_all  # noqa: E402
from ltcm.mind import (  # noqa: E402
    DEFAULT_CONFIG,
    LOCKED,
    FirmMind,
    aggregate,
    evidence_text,
    table_text,
)
from ltcm.service import PACKAGE_DIR, default_config  # noqa: E402


class ReadOnlyLog:
    """The two reads a pass makes, on a connection that cannot write."""

    def __init__(self, path: Path):
        self._db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self._db.row_factory = sqlite3.Row

    def read(self, *, stream: str | None = None, kind: str | None = None, limit: int = 1000, newest: bool = False, **_: Any) -> list[Event]:
        clauses, params = ["1 = 1"], []
        if stream is not None:
            clauses.append("stream = ?")
            params.append(stream)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        params.append(max(1, min(int(limit), 10_000)))
        order = "DESC" if newest else "ASC"
        rows = self._db.execute(
            f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY seq {order} LIMIT ?", params
        ).fetchall()
        events = [
            Event(r["seq"], r["id"], r["stream"], r["kind"], r["at"], bool(r["public"]), json.loads(r["payload"]), r["previous_hash"], r["digest"])
            for r in rows
        ]
        return events[::-1] if newest else events

    def close(self) -> None:
        self._db.close()


def families(config: dict[str, Any]) -> dict[str, str]:
    try:
        return {m.id: m.family for m in load_all(Path(config.get("desks_dir") or (PACKAGE_DIR / "desks")))}
    except Exception:
        return {}


def print_book(mind: FirmMind, outcomes: list) -> None:
    rules = mind.rules()
    print(f"\n# The rule book ({len(rules)} rules), re-scored now on what its proposers never read")
    if not rules:
        print("(empty)")
    for rule in rules:
        ok, reason, score = mind.retention(rule, outcomes)
        print(f"- {rule['id']} [{rule['direction']}] {evidence_text(score)}: {'holds' if ok else 'would retire: ' + reason}")
        print(f"    {rule['statement']}")
        print(f"    filter {json.dumps(rule['filter'], sort_keys=True)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="read-only (the default)")
    mode.add_argument("--apply", action="store_true", help="run a full pass: write the book and publish")
    parser.add_argument("--ask", action="store_true", help="with --dry-run: also call the model and score its proposals")
    parser.add_argument("--root", default=str(ROOT), help="the checkout that holds .data/ltcm")
    parser.add_argument("--cells", type=int, default=None, help="rows of the aggregate table to print")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    capital_dir = root / ".data" / "ltcm"
    events_path = capital_dir / "events.sqlite"
    if not events_path.exists():
        print(f"no event log at {events_path}", file=sys.stderr)
        return 2
    config = default_config()
    mind_config = {**DEFAULT_CONFIG, **dict(config.get("mind") or {})}
    at = now_iso()
    roster = families(config)

    if args.apply:
        from ltcm.events import EventLog
        from ltcm.provider import Provider

        log = EventLog(events_path)
        provider = Provider(
            capital_dir / "provider.sqlite",
            log=log,
            floor_cap_usd_per_day=config.get("floor_cap_max_usd_per_day", "60"),
            reserve_floor_usd=config.get("reserve_floor_usd", "10"),
        )
        try:
            mind = FirmMind(log, path=capital_dir / "mind.json", provider=provider, config=mind_config, families=lambda: roster, alert=lambda level, text: print(f"[{level}] {text}", file=sys.stderr))
            summary = mind.run(at, force=True)
            if summary.get("skipped") == LOCKED:
                print(f"refused: {LOCKED} (the floor's pass is running); try again in a minute", file=sys.stderr)
                return 1
            print(json.dumps(summary, indent=2, sort_keys=True))
            outcomes, _ = mind.outcomes()
            print_book(mind, outcomes)
            return 0 if not summary.get("failed") else 1
        finally:
            provider.close()
            log.close()

    log = ReadOnlyLog(events_path)
    provider = None
    if args.ask:
        from ltcm.provider import Provider

        provider = Provider(
            capital_dir / "provider.sqlite",
            floor_cap_usd_per_day=config.get("floor_cap_max_usd_per_day", "60"),
            reserve_floor_usd=config.get("reserve_floor_usd", "10"),
        )
    mind = FirmMind(log, path=capital_dir / "mind.json", provider=provider, config=mind_config, families=lambda: roster, alert=lambda level, text: print(f"[{level}] {text}", file=sys.stderr), register=False)
    outcomes, latest = mind.outcomes()
    desks = len({o.desk_id for o in outcomes})
    read, held_out, cut = mind.split(outcomes)
    print(
        f"# The Firm Mind, dry run at {at}: {len(outcomes)} scoreable outcomes from {desks} desks (newest outcome seq {latest}); "
        f"a pass would show the scientist {len(read)} and test its proposals on the {len(held_out)} after seq {cut}"
    )
    cells = aggregate(outcomes, args.cells or int(mind_config["cells"]))
    print(f"\n# Cells (top {len(cells)} by |pnl| and by n)")
    print(table_text(cells))
    print_book(mind, outcomes)
    if args.ask:
        summary = mind.run(at, persist=False, publish=False, force=True)
        provider.close()
        if summary.get("skipped") == LOCKED:
            print(f"refused: {LOCKED} (the floor's pass is running); try again in a minute", file=sys.stderr)
            log.close()
            return 1
        print("\n# The scientist's proposals")
        for row in summary.get("proposals") or []:
            print(f"- {row.get('id')}: {row.get('status')} ({row.get('evidence') or ''}) {row.get('reason')}")
        print(json.dumps({k: summary.get(k) for k in ("asked", "added", "revised", "retired", "rules")}, sort_keys=True))
    log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
