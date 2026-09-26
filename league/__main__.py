"""Run and inspect the options House: run, tick, status, verify, stop, start.

PAUSE keeps reconciliation and exits running while refusing new paid work and entries.
STOP ends the process. Owner deployment is explicit; the automatic updater defaults off.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import faulthandler
import json
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path
from .service import REPO, build, load_config


@contextmanager
def slow_tick_trace(root):
    path = Path(root) / "slow-tick.log"
    with path.open("a") as trace:
        path.chmod(0o600)
        faulthandler.dump_traceback_later(180, file=trace)
        try:
            yield
        finally:
            faulthandler.cancel_dump_traceback_later()


def read_status(root: Path) -> dict:
    out = {}
    for name in ("health.json", "swarm.heartbeat", "data/nightly.heartbeat"):
        try:
            out[name] = json.loads((root / name).read_text())
        except (OSError, ValueError):
            out[name] = None
    out.update(stopped=(root / "STOP").exists(), paused=(root / "PAUSE").exists())
    return out


def verify(root: Path, *, canary: bool = False) -> dict:
    from .ledger import Ledger
    if not (root / "ledger.sqlite").is_file():
        raise RuntimeError("no ledger exists at this state root")
    ledger = Ledger(root / "ledger.sqlite")
    try:
        rows = ledger.verify()
        if canary and not ledger.read(kinds="canary.proof", limit=1):
            raise RuntimeError("the canary has no successful synthetic options proof")
    finally:
        ledger.close()
    stores = {}
    for path in sorted(root.glob("*.sqlite")):
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            check = db.execute("PRAGMA quick_check").fetchall()
        if check != [("ok",)]:
            raise RuntimeError(f"{path.name} failed SQLite integrity verification")
        stores[path.name] = "ok"
    return {"ledger_rows_verified": rows, "stores": stores}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="league", description=__doc__)
    parser.add_argument("command", choices=("run", "tick", "status", "verify", "stop", "start"))
    parser.add_argument("--root", default=str(REPO / ".data" / "league"))
    parser.add_argument("--tape", default=None)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--no-research", action="store_true")
    parser.add_argument("--local-sandbox", action="store_true")
    parser.add_argument("--canary", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root)
    canary = args.canary or os.environ.get("LEAGUE_CANARY") == "1"
    if canary and args.root == parser.get_default("root"):
        parser.error("a canary needs its own --root")
    if args.command == "stop":
        root.mkdir(parents=True, exist_ok=True)
        (root / "STOP").write_text("stopped by the operator\n")
        print("STOP written; the loop ends after the tick in hand")
        return 0
    if args.command == "start":
        (root / "STOP").unlink(missing_ok=True)
        print("STOP removed")
        return 0
    if args.command == "status":
        print(json.dumps(read_status(root), indent=1))
        return 0
    if args.command == "verify":
        print(json.dumps(verify(root, canary=canary), indent=1))
        return 0
    config = load_config()
    if config.get("real_money") is True and args.local_sandbox and not canary:
        parser.error("real money requires the sealed Sail program runner")
    house = build(root, config=config, local_sandbox=args.local_sandbox,
                  research=not args.no_research, publish=not args.no_publish, tape=args.tape, canary=canary)
    try:
        if canary:
            from .canary import verify_runtime
            house.ledger.append("canary.proof", verify_runtime())
        if args.command == "tick":
            print(json.dumps(house.tick(), default=str))
            return 0
        stopping = {"now": False}
        def terminate(*_):
            stopping["now"] = True
            house.begin_close()
        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        while not stopping["now"] and not house.stopped():
            started = time.time()
            try:
                with slow_tick_trace(root):
                    summary = house.tick()
                print(json.dumps(summary, default=str), flush=True)
            except Exception as error:
                house.alert("error", f"tick failed: {type(error).__name__}: {str(error)[:300]}")
                print(f"tick failed: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            wake_at = time.time() + max(1.0, house.settings.tick_seconds - (time.time() - started))
            while not stopping["now"] and not house.stopped() and time.time() < wake_at:
                time.sleep(min(1.0, max(0.0, wake_at - time.time())))
    finally:
        house.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
