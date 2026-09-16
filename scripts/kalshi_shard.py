#!/usr/bin/env python3
"""Kalshi exchange shards: see the balance on each, and move collateral between them.

Kalshi runs several exchange instances ("shards"): 0 is the default, 1 carries exotics, 2 crypto
and commodities, 3 some sports. Orders auto-route by ticker, but the shard must already hold
collateral, or the venue answers `insufficient_shard_balance` ("Exchange user not found"), which
is what the floor's first live order on an hourly BTC market got on Sept 16, 2026.

    python3 scripts/kalshi_shard.py balance                 # balance and the per-shard breakdown
    python3 scripts/kalshi_shard.py transfer --usd 100 --to 2   # from shard 0 to shard 2
    python3 scripts/kalshi_shard.py transfer --usd 100 --from 2 --to 0

Signs through the Cloudflare gateway with GATEWAY_TOKEN from `.env`, like the floor does; no
venue key is read here. A transfer is money moving inside the owner's own Kalshi account: it
cannot withdraw, and it can be moved back. Prints no secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ltcm.adapters import GatewaySigner, KalshiCredentials, VenueClient, kalshi  # noqa: E402
from ltcm.data import HttpTransport  # noqa: E402
from ltcm.service import load_env  # noqa: E402

GATEWAY_URL = "https://ltcm-gateway.blake-woods-personal-site.workers.dev"
TRANSFER_PATH = "/portfolio/intra_exchange_instance_transfer"
SHARDS = {0: "default (economics, weather, politics)", 1: "exotics", 2: "crypto and commodities", 3: "tennis, baseball, basketball"}


def broker() -> kalshi.KalshiBroker:
    env = load_env(ROOT / ".env")
    token = env.get("GATEWAY_TOKEN")
    if not token:
        raise SystemExit("GATEWAY_TOKEN is not in .env")
    config = json.loads((ROOT / "ltcm" / "config.json").read_text(encoding="utf-8"))
    url = str(config.get("gateway_url") or GATEWAY_URL)
    client = VenueClient(HttpTransport(), gateway_url=url, gateway=GatewaySigner(token), venue="kalshi")
    return kalshi.KalshiBroker(KalshiCredentials("gateway", GatewaySigner(token)), client=client)


def cmd_balance(args: argparse.Namespace) -> int:
    payload = broker()._call("GET", "/portfolio/balance", what="kalshi balance", ok=(200,))
    print("balance_dollars:", payload.get("balance_dollars"), "| portfolio_value:", payload.get("portfolio_value"))
    rows = payload.get("balance_breakdown") or []
    if not rows:
        print("no per-shard breakdown in the response (a subaccount-restricted key omits it)")
    for row in rows:
        print("  shard", row.get("exchange_index"), "|", json.dumps({k: v for k, v in row.items() if k != "exchange_index"}), "|", SHARDS.get(row.get("exchange_index"), ""))
    return 0


def cmd_transfer(args: argparse.Namespace) -> int:
    try:
        usd = Decimal(str(args.usd))
    except InvalidOperation:
        raise SystemExit("--usd must be a number")
    if usd <= 0 or usd > Decimal("5000"):
        raise SystemExit("--usd must be between 0 and 5000")
    if args.src == args.to:
        raise SystemExit("--from and --to must differ")
    centicents = int((usd * 10_000).to_integral_value())  # the API counts hundredths of a cent
    body = {
        "source": "event_contract",
        "destination": "event_contract",
        "amount": centicents,
        "source_exchange_shard": int(args.src),
        "destination_exchange_shard": int(args.to),
    }
    print(f"moving ${usd:.2f} from shard {args.src} ({SHARDS.get(args.src, '')}) to shard {args.to} ({SHARDS.get(args.to, '')})")
    payload = broker()._call("POST", TRANSFER_PATH, body=body, what="kalshi shard transfer", ok=(200, 201))
    print("transfer_id:", (payload or {}).get("transfer_id"))
    print("a cross-shard move runs in up to three steps that are not undone on failure; check `balance` after")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("balance", help="balance and per-shard breakdown").set_defaults(func=cmd_balance)
    move = sub.add_parser("transfer", help="move collateral between shards")
    move.add_argument("--usd", required=True, help="dollars to move")
    move.add_argument("--from", dest="src", type=int, default=0, help="source shard (default 0)")
    move.add_argument("--to", type=int, required=True, help="destination shard (crypto is 2)")
    move.set_defaults(func=cmd_transfer)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
