#!/usr/bin/env python3
"""Read-only economics of the options run. Closed-book trading P&L includes all fills and fees.

Use --root /workspace/state. Open/unpriced/ambiguous inventory has unknown P&L because this
command reads no licensed quotes. The live publisher supplies its contemporaneous full-book mark.
Swarm attributed costs are shown by kind; Sail's balance-debit meter is separate to avoid double
counting infrastructure estimates. Net profit after every input cost is unknown until all costs
and remaining inventory have complete evidence.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def ro(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    db.execute('PRAGMA query_only=1')
    return db

def build(root):
    from league.trading_profit import snapshot
    root = Path(root)
    at = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    result = {'as_of':at,'trading':None,'attributed_spend_usd':None,'sail_meter_usd':None,
              'net_after_all_inputs_usd':None,'basis':'all real option cashflows; marks unknown without the live quote snapshot'}
    never_traded = False
    if (root/'ledger.sqlite').exists():
        with closing(ro(root/'ledger.sqlite')) as db:
            # Only a readable complete current ledger with no real fill can establish a never-traded book.
            rows = db.execute("SELECT kind,payload FROM ledger WHERE kind IN ('live.fill','book.fill','book.settle','ops.budget')")
            sail = 0.0; seen_meter = False; fills = False
            for kind, raw in rows:
                payload = json.loads(raw)
                if kind == 'live.fill' or (kind in ('book.fill','book.settle') and payload.get('real_money') is True): fills = True
                if kind == 'ops.budget' and payload.get('what') == 'sail':
                    sail += float(payload['spent_usd']); seen_meter = True
            never_traded = not fills
            result['sail_meter_usd'] = round(sail,6) if seen_meter else None
    result['trading'] = snapshot(root, None, at=at, never_traded=never_traded)
    if (root/'swarm.sqlite').exists():
        with closing(ro(root/'swarm.sqlite')) as db:
            result['attributed_spend_usd'] = dict(db.execute('SELECT kind,SUM(usd) FROM spend GROUP BY kind'))
            result['trials'] = db.execute('SELECT COALESCE(SUM(trials),0) FROM runs').fetchone()[0]
    return result

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='/workspace/state')
    p.add_argument('--json',action='store_true')
    args = p.parse_args(argv)
    print(json.dumps(build(args.root),indent=2,sort_keys=True))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
