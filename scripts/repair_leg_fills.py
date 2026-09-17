#!/usr/bin/env python3
"""Repair Kalshi fills the tape recorded on the other leg from their order (Sept 17, 2026).

Kalshi reports a sale of YES as a purchase of NO at the complement. Until the gateway put each
fill on its order's leg (`Gateway._on_order_leg`), the floor's exit that sold 34 YES of a Warsh
market at 15 cents was on the tape as 34 NO bought at 85: the ledger held both legs, the venue
neither. This script runs ON THE FLOOR BOX. For every real Kalshi fill attributed to a floor
order whose leg differs, it appends `<fill_id>:leg-reversal` (the recorded trade undone, at zero
P&L) and `<fill_id>:leg-corrected` (the same trade on the order's leg at the complement price,
side flipped; the fee stays charged once, on the original). The originals stay, as the append-only log requires.

    cd /workspace && .venv/bin/python scripts/repair_leg_fills.py            # dry run
    cd /workspace && .venv/bin/python scripts/repair_leg_fills.py --apply

Idempotent: a fill that already has a corrected copy is skipped.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ltcm.events import EventLog, now_iso  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--log", default=str(ROOT / ".data" / "ltcm" / "events.sqlite"))
    args = parser.parse_args(argv)
    log = EventLog(args.log)
    try:
        legs = {}
        for event in log.read(kind="broker.order", limit=100_000):
            p = event.payload
            ins = p.get("instrument") or {}
            if p.get("order_id") and ins.get("asset_class") == "event":
                legs[str(p["order_id"])] = (str(ins.get("right") or "yes").lower(), str(ins.get("market_id") or ins.get("symbol") or "").upper(), p.get("side"))
        fills = log.read(kind="broker.fill", limit=100_000)
        done = {str(e.payload.get("fill_id") or "") for e in fills}
        todo = []
        for event in fills:
            p = event.payload
            fid = str(p.get("fill_id") or "")
            if p.get("venue") != "kalshi" or p.get("shadow") or p.get("settlement") or not p.get("desk_id") or ":" in fid:
                continue
            leg = legs.get(str(p.get("order_id") or ""))
            ins = p.get("instrument") or {}
            if leg is None or ins.get("asset_class") != "event":
                continue
            want, market, order_side = leg
            have = str(ins.get("right") or "yes").lower()
            mine = str(ins.get("market_id") or ins.get("symbol") or "").upper()
            if want == have or (market and mine != market) or f"{fid}:leg-corrected" in done:
                continue
            todo.append((event, p, want, order_side))
        for event, p, want, order_side in todo:
            price = Decimal(str(p["price"]))
            flipped = "sell" if p["side"] == "buy" else "buy"
            print(f"{p['desk_id']} {p['instrument'].get('market_id')}: recorded {p['side']} {p['quantity']} {p['instrument'].get('right')} @ {p['price']} "
                  f"-> {flipped} {p['quantity']} {want} @ {Decimal(1) - price} (order side {order_side})")
            if not args.apply:
                continue
            at = str(p.get("at") or event.at)
            reversal = dict(p, fill_id=f"{p['fill_id']}:leg-reversal", id=f"{p['fill_id']}:leg-reversal",
                            side="sell" if p["side"] == "buy" else "buy", fee="0", repair="leg")
            corrected = dict(p, fill_id=f"{p['fill_id']}:leg-corrected", id=f"{p['fill_id']}:leg-corrected",
                             side=flipped, price=format(Decimal(1) - price, "f"), fee="0", repair="leg",
                             instrument=dict(p["instrument"], right=want))
            log.append("broker:kalshi", "broker.fill", reversal, id=f"fill:kalshi:{reversal['fill_id']}", at=event.at)
            log.append("broker:kalshi", "broker.fill", corrected, id=f"fill:kalshi:{corrected['fill_id']}", at=event.at)
        print(f"{len(todo)} fill(s) on the wrong leg; {'repaired' if args.apply else 'dry run'} at {now_iso()}")
        return 0
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())
