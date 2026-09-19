"""python3 -m league <command>

    run       the House loop: tick, sleep, tick, until a STOP file appears in the state directory
    tick      one tick, then exit (prints its summary)
    found     seed the founding population (idempotent)
    status    the league table, the books and the budget, as JSON
    verify    recompute the ledger's hash chain and reconcile every book to its venue
    stop      write the STOP file; the loop ends after the tick in hand
    start     remove the STOP file

Options: --root DIR (state directory, default .data/league), --tape NAME (publish to a test tape),
--no-publish, --no-research, --local-sandbox (developer machines only; never with real money).
Real money is a line in league/config.json (`"real_money": true`) that only the owner changes,
and the gateway's kill switch stands behind it.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

from .service import REPO, build, load_config


#: What a canary founds: one agent per venue family is enough to exercise every path.
CANARY_SEEDS = ["crypto-reversion", "favorites-maker"]


def table(house) -> dict:
    rows = []
    for agent in house.registry.living():
        book = house.book_of(agent)
        account = book.account(agent.id) if book is not None and agent.id in book.accounts else None
        rows.append({
            "agent": agent.id, "family": agent.family, "niche": agent.niche, "generation": agent.generation,
            "rung": house.evaluator.rung(agent.id), "credits_usd": format(house.economy.balance(agent.id), "f"),
            "book": book.name if book else None,
            "equity": format(book.equity(agent.id), "f") if account else None,
            "blocks": len(house.evaluator.blocks(agent.id)),
        })
    return {
        "living": rows,
        "dead": [{"agent": a.id, "cause": a.cause, "died_at": a.died_at} for a in house.registry.dead()],
        "books": {name: {"real_money": b.real_money, "frozen": b.frozen, "open_orders": len(b.open_orders()), "equity": format(b.total_equity(), "f")} for name, b in house.books.items()},
        "budget": None if house.budget is None else {"mode": house.budget.mode, "month_usd": format(house.budget.month_spend(), "f")},
        "ledger": {"rows": house.ledger.head()[0]},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="league", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["run", "tick", "found", "status", "verify", "stop", "start"])
    parser.add_argument("--root", default=str(REPO / ".data" / "league"))
    parser.add_argument("--tape", default=None)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--no-research", action="store_true")
    parser.add_argument("--local-sandbox", action="store_true")
    parser.add_argument("--seeds", default=None, help="comma-separated seed names for `found` (default: all)")
    parser.add_argument("--canary", action="store_true", help="a House that can hurt nothing: simulated paper venue, no publishing, no research")
    args = parser.parse_args(argv)
    canary = args.canary or os.environ.get("LEAGUE_CANARY") == "1"
    if canary and args.root == parser.get_default("root"):
        parser.error("a canary needs its own --root")
    root = Path(args.root)
    stop_file = root / "STOP"
    if args.command == "stop":
        root.mkdir(parents=True, exist_ok=True)
        stop_file.write_text("stopped by the operator\n", encoding="utf-8")
        print("STOP written; the loop ends after the tick in hand")
        return 0
    if args.command == "start":
        stop_file.unlink(missing_ok=True)
        print("STOP removed")
        return 0
    config = load_config()
    if config.get("real_money") and args.local_sandbox:
        parser.error("real money needs sealed Sailboxes: drop --local-sandbox")
    house = build(root, config=config, local_sandbox=args.local_sandbox, research=not args.no_research, publish=not args.no_publish, tape=args.tape, canary=canary)
    try:
        if args.command == "found":
            born = house.found(args.seeds.split(",") if args.seeds else None)
            print(json.dumps({"born": [a.id for a in born]}))
        elif args.command == "tick":
            if canary and not house.registry.living():
                house.found(CANARY_SEEDS)
            print(json.dumps(house.tick(), default=str))
            house.wait(300 if canary else 0)  # a canary proves its replays too; a House tick never waits
            house.sandbox.sleep_all()
        elif args.command == "status":
            print(json.dumps(table(house), indent=1))
        elif args.command == "verify":
            rows = house.ledger.verify()
            books = {name: vars(book.reconcile()) for name, book in house.books.items()}
            print(json.dumps({"ledger_rows_verified": rows, "books": books}, indent=1, default=str))
            if canary:
                # `verify` is the canary's last act: its throwaway boxes are destroyed, not left asleep.
                for agent in list(getattr(house.sandbox, "_state", {}).get("boxes", {})):
                    house.sandbox.retire(agent)
            return 0 if all(b["ok"] for b in books.values()) else 1
        else:
            stopping = {"now": False}
            signal.signal(signal.SIGTERM, lambda *_: stopping.update(now=True))
            if not house.registry.living():
                house.found()
            while not stopping["now"] and not stop_file.exists():
                started = time.time()
                try:
                    summary = house.tick()
                    print(json.dumps({k: summary[k] for k in ("at", "woke", "orders", "deaths", "reconciled", "budget")}, default=str), flush=True)
                except Exception as exc:  # noqa: BLE001 - the loop outlives any one tick
                    house.alert("error", f"tick failed: {type(exc).__name__}: {str(exc)[:300]}")
                    print(f"tick failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                time.sleep(max(1.0, house.settings.tick_seconds - (time.time() - started)))
            house.sandbox.sleep_all()
    finally:
        house.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
