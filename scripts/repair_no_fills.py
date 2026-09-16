#!/usr/bin/env python3
"""Repair Kalshi fills the tape recorded with the wrong side (Sept 16, 2026).

Kalshi writes a fill's `action` on the YES book: a fill of the floor's resting NO bid comes
back as `side: no, action: sell, book_side: ask`, and until commit `kalshi: action on the
YES book` the parser trusted `action`, so every NO buy since 05:00 UTC landed on the tape as
a sell and the desk ledgers went short contracts the venue holds long. This script runs ON
THE FLOOR BOX: it reads Kalshi's own fills again (the fixed parser reads them right), finds
every tape fill whose side disagrees, and appends two corrected copies per fill under new
event ids: `<id>:reversal` (the same trade with the side the tape should have had, which
cancels the wrong entry at zero P&L) and `<id>:corrected` (the trade itself). The ledgers
fold both on the next restart. The original events stay, as the append-only log requires.

    cd /workspace && .venv/bin/python scripts/repair_no_fills.py            # dry run
    cd /workspace && .venv/bin/python scripts/repair_no_fills.py --apply

Idempotent: a fill that already has a corrected copy is skipped.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ltcm.events import EventLog  # noqa: E402
import kalshi_shard  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the corrected copies (default: dry run)")
    parser.add_argument("--since", default="2026-09-16T04:00:00Z", help="read venue fills from this instant")
    parser.add_argument("--log", default=str(ROOT / ".data" / "ltcm" / "events.sqlite"))
    args = parser.parse_args(argv)
    broker = kalshi_shard.broker()
    truth = {}
    for fill in broker.fills(since=args.since):
        truth[str(fill.id)] = fill
    print(f"{len(truth)} venue fills read with the fixed parser")
    log = EventLog(args.log)
    fills = log.read(kind="broker.fill", limit=50_000)
    # The ledger folds each fill_id once, so a copy needs its own: `<fill_id>:reversal` and
    # `<fill_id>:corrected`. (A first pass on Sept 16 copied the original fill_id and the
    # ledgers ignored the copies.)
    corrected = {str(e.payload.get("fill_id"))[: -len(":corrected")] for e in fills if str(e.payload.get("fill_id", "")).endswith(":corrected")}
    todo = []
    for event in fills:
        p = event.payload
        if p.get("venue") != "kalshi" or p.get("shadow") or p.get("settlement") or not p.get("desk_id"):
            continue  # a fill without a desk folds into no ledger; its attributed copy carries the intent's side
        fill_id = str(p.get("fill_id") or "")
        if ":" in fill_id or str(event.id).endswith((":corrected", ":reversal", ":corrected:2", ":reversal:2")):
            continue
        if fill_id in corrected or fill_id not in truth:
            continue
        right = str((p.get("instrument") or {}).get("right") or "").lower()
        true_side = truth[fill_id].side
        if p.get("side") == true_side:
            continue
        todo.append((event, true_side, right))
    print(f"{len(todo)} tape fill(s) carry the wrong side")
    for event, true_side, right in todo:
        p = event.payload
        print(f"  {event.at} {p.get('desk_id') or '-'} tape {p.get('side')} {right} {p.get('quantity')} {(p.get('instrument') or {}).get('market_id')} @ {p.get('price')} -> {true_side}")
        if args.apply:
            reversal = {**p, "fill_id": f"{fill_id}:reversal", "side": true_side, "fee": "0", "corrected_from": event.id, "note": "reverses a fill recorded on the wrong side"}
            log.append(event.stream, "broker.fill", reversal, id=f"{event.id}:reversal:2", at=event.at)
            fixed = {**p, "fill_id": f"{fill_id}:corrected", "side": true_side, "corrected_from": event.id}
            log.append(event.stream, "broker.fill", fixed, id=f"{event.id}:corrected:2", at=event.at)
    print("applied" if args.apply else "dry run", len(todo))
    if args.apply and todo:
        print("restart the loop so the ledgers refold:  python3 scripts/floor_box.py deploy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
