#!/usr/bin/env python3
"""Private project economics. Collect local metadata read-only, or reconcile receipts into an immutable report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from league.project_economics import collect, persist, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    part = sub.add_parser("collect", help="print redacted state metadata; no writes or network calls")
    part.add_argument("--state", type=Path, required=True)
    part = sub.add_parser("report", help="reconcile independently timestamped receipts")
    part.add_argument("--evidence", type=Path, required=True)
    part.add_argument("--boxes", type=Path, help="provider box-cost receipt including per-box app ids")
    part.add_argument("--app-id", required=True)
    part.add_argument("--external", type=Path, help="attributed external engineering/inference/other-cost coverage, if known")
    part.add_argument("--subscription-rates", type=Path, help="optional existing subscriptions_monthly_usd mapping")
    part.add_argument("--output-root", type=Path, required=True, help="private report directory, separate from production state")
    args = parser.parse_args()
    def read(path):
        return json.loads(path.read_text()) if path else None
    if args.command == "collect":
        result = collect(args.state)
    else:
        evidence, boxes, external, rates = (read(path) for path in (args.evidence, args.boxes, args.external, args.subscription_rates))
        result = report(evidence, boxes, app_id=args.app_id, external=external, subscription_rates=rates)
        for receipt in (evidence, boxes, external, rates):
            if receipt is not None:
                persist(args.output_root / "receipts", receipt)
        path = persist(args.output_root, result)
        result = {"snapshot": str(path), "as_of": result["as_of"], "known_input_subtotal_usd": result["known_input_subtotal_usd"],
                  "project_net_usd": result["project_net_usd"], "complete": result["complete"], "unresolved": result["unresolved"]}
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
