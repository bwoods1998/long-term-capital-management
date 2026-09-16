#!/usr/bin/env python3
"""Attribute the live Kalshi fills the floor recorded without a desk (Sept 16, 2026).

Before commit c2 of Sept 16 the gateway wrote swept Kalshi fills exactly as the venue named
them: with Kalshi's order id and no desk, and with a NO buy read as a sell. No desk ledger ever
saw them, so the live desks showed flat books while the venue held seven positions. This script
runs ON THE FLOOR BOX (the deploy uploads it), reads Kalshi's own order list to map each
venue order id to the floor's order, and appends a corrected copy of every unattributed fill
under a new event id (`fill:kalshi:<fill_id>:attributed`) carrying the desk, the floor's order
id, the intent id and the side the floor actually traded. The desk ledgers fold the copies in;
the original events stay where they were, as the append-only log requires.

    cd /workspace && .venv/bin/python scripts/attribute_fills.py            # dry run
    cd /workspace && .venv/bin/python scripts/attribute_fills.py --apply

Idempotent: a fill that already has an attributed copy is skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ltcm.events import EventLog  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import kalshi_shard  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the corrected copies (default: dry run)")
    parser.add_argument("--log", default=str(ROOT / ".data" / "ltcm" / "events.sqlite"))
    args = parser.parse_args(argv)

    broker = kalshi_shard.broker()
    venue_to_ours: dict[str, str] = {}
    for status in ("resting", "executed", "canceled"):
        try:
            for order in broker.orders(status=status, limit=200):
                if order.broker_order_id:
                    venue_to_ours[str(order.broker_order_id)] = order.id
        except Exception as exc:
            print(f"could not list {status} orders: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(f"{len(venue_to_ours)} venue orders mapped to floor orders")

    log = EventLog(args.log)
    orders = {}
    for event in log.read(kind="broker.order", limit=20_000):
        row = orders.setdefault(event.payload.get("order_id"), {})
        for key in ("desk_id", "intent_id", "side"):
            if event.payload.get(key):
                row[key] = event.payload[key]
    fills = log.read(kind="broker.fill", limit=20_000)
    have_copy = {e.payload.get("fill_id") for e in fills if str(e.id).endswith(":attributed")}
    todo = []
    for event in fills:
        p = event.payload
        if p.get("shadow") or p.get("settlement") or p.get("desk_id") or str(event.id).endswith(":attributed"):
            continue
        if p.get("fill_id") in have_copy:
            continue
        ours = venue_to_ours.get(str(p.get("order_id") or ""))
        if ours is None:
            print("  no floor order for venue order", str(p.get("order_id"))[:24], "fill", p.get("fill_id"))
            continue
        row = orders.get(ours) or {}
        if not row.get("desk_id"):
            print("  no desk on record for", ours)
            continue
        todo.append((event, ours, row))
    print(f"{len(todo)} unattributed live fill(s) to copy")
    for event, ours, row in todo:
        p = dict(event.payload)
        p.update({
            "order_id": ours,
            "venue_order_id": event.payload.get("order_id"),
            "desk_id": row["desk_id"],
            "intent_id": row.get("intent_id"),
            # The floor's orders were all buys of the leg they name; a swept NO buy had been
            # read as a sell.
            "side": row.get("side") or p.get("side"),
            "attributed_from": event.id,
        })
        print(f"  {event.at} {row['desk_id']} {p['side']} {p.get('quantity')} {p.get('instrument', {}).get('market_id')} {p.get('instrument', {}).get('right')} @ {p.get('price')} <- {ours}")
        if args.apply:
            log.append(event.stream, "broker.fill", p, id=f"{event.id}:attributed", at=event.at)
    print("applied" if args.apply else "dry run", len(todo))
    if args.apply and todo:
        print("restart the loop so the ledgers refold and the settlement poll scores the closed markets:  python3 scripts/floor_box.py deploy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
