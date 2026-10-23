"""THE BUG STOP, LATCHED (the owner's goal V3, wall 1: "a bug stop that pauses new entries after a 25% loss in one session
until you have read why"; release 1019m, the independent review's blocker, A139).

The options path's daily stop (league/live/money.py `Stops`, `options_money.daily_stop_share` 0.25 since release 1019l)
trips on a settled reading whose day's P&L is at or past 25% of the day's base, and blocks every new real entry FOR THAT
SESSION: its first reading of the next session clears it. V3's wall holds the pause UNTIL THE CAPTAIN HAS READ WHY. So
the equity book (league/equity/live.py `EquityBook._bug_stop`, every minute, in the House's own thread) latches it: on
the first minute it reads the options path's stop state (`STOPS`, the live state's `stops` key-value) tripped for a
session it has not latched yet, it writes `LATCH` ({day, why, at, released: None}) and alerts. While the latch stands
unreleased the book's freeze (`EquityBook.frozen`) names it, and the House's real-money block reads that freeze for
every lane (league/live/step.py `real_block`: "equity reconciliation: <why>"), so EVERY NEW REAL ENTRY, options and
shares, stays refused on every later session; exits and cancels go on as under any freeze. Only the captain's release
lifts it, with what was read (`RELEASE`, written by this command, read and done once by the book's next minute, which
keeps the latch's row with its release so the same session's stop never latches again). The latch lives outside
league/live, so the options execution fingerprint does not move.

    python3 -m league.equity.bugstop --root /workspace/state                                   # the latch, read only
    python3 -m league.equity.bugstop --root /workspace/state --release "<what was read: why the loss happened>"

Nothing here sends an order or reads a venue: it reads and writes the live state (`<root>/live.sqlite`).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Mapping

#: The latch: {"day": the session the daily stop tripped, "why": its reason, "at": epoch seconds latched, "released":
#: None | {"at", "by", "why"}}.
LATCH = "eq_bug_stop"
#: The captain's release, written by `main` and read by the book's next minute ({"why", "at", "by"}).
RELEASE = "owner_equity_release_bug_stop"
#: The options path's stop state (league/live/money.py `Stops.as_state`, persisted by league/live/step.py).
STOPS = "stops"
#: The command a latch's reason names.
COMMAND = 'python3 -m league.equity.bugstop --root <state> --release "<what was read>"'


def tripped(stops: Any) -> tuple[str, str] | None:
    """(session day, why) when the options path's stop state says its daily stop is tripped, else None."""
    if not isinstance(stops, Mapping) or not stops.get("daily_tripped") or not stops.get("day"):
        return None
    return str(stops["day"]), str(stops.get("daily_why") or "the daily stop tripped")


def standing(latch: Any) -> bool:
    """Whether a latch holds new entries (written and not released)."""
    return isinstance(latch, Mapping) and bool(latch.get("day")) and not latch.get("released")


def reason(latch: Any) -> str:
    """The freeze's words for a standing latch ("" for none)."""
    if not standing(latch):
        return ""
    return (f"THE BUG STOP (goal V3): {str(latch.get('why') or '')[:300]} on {latch.get('day')}; every new real entry "
            f"is held until the captain reads why and releases it ({COMMAND})")


def ask(why: str) -> dict[str, Any]:
    """The release's key-value; the reading is required (it is recorded with the release)."""
    why = " ".join(str(why or "").split())
    if not why:
        raise SystemExit("say what was read: the reason the session lost 25% is recorded with the release")
    return {"why": why[:400], "at": time.time(), "by": "the captain (python -m league.equity.bugstop)"}


def main(argv: list[str] | None = None) -> dict[str, Any]:
    from ..live.state import STATE_FILE, LiveState

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True, help="The House's state root (on the box: /workspace/state).")
    parser.add_argument("--release", metavar="WHAT_WAS_READ", help="Release the bug stop, saying what was read.")
    args = parser.parse_args(argv)
    path = args.root / STATE_FILE
    if not path.exists():
        raise SystemExit(f"no live state at {path}")
    state = LiveState(path)
    try:
        if args.release is not None:
            if not standing(state.get(LATCH)):
                raise SystemExit("no standing bug stop to release")
            state.put(RELEASE, ask(args.release))
        out = {"latch": state.get(LATCH), "pending_release": state.get(RELEASE),
               "stops": {k: (state.get(STOPS) or {}).get(k) for k in ("day", "daily_tripped", "daily_why")}}
    finally:
        state.close()
    print(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    main()


__all__ = ["LATCH", "RELEASE", "STOPS", "COMMAND", "tripped", "standing", "reason", "ask", "main"]
