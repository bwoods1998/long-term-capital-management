#!/usr/bin/env python3
"""The operator's view of the House's jobs during the unattended clock: read the House's private receipts file through
the Sail Files API (a GET of one file; never an exec, never a write) and print a summary.

    python3 scripts/desk_receipts.py                 # <state>/receipts/latest.json
    python3 scripts/desk_receipts.py 2026-10-06      # that UTC day's file
    python3 scripts/desk_receipts.py --json          # the whole file, as JSON
    python3 scripts/desk_receipts.py --box sb_...    # another box than the one .data/ltcm/box.json records

The receipts file is written by the House every ten minutes (`league/ops/receipts.py`): every job occurrence of the
day with its receipt, a health summary, the day's deploy rows, the swarm's spend and the budget's state. It carries the
House's private figures: print it on the owner's terminal only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

BOX_RECORD = REPO / ".data" / "ltcm" / "box.json"
STATE = "/workspace/state/receipts"
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def recorded_box() -> str | None:
    try:
        return json.loads(BOX_RECORD.read_text(encoding="utf-8")).get("box_id")
    except (OSError, ValueError, AttributeError):
        return None


def fetch(client: Any, box: str, day: str | None = None) -> dict[str, Any]:
    """The receipts file of `day` (or latest.json) from the House box, through the Files API."""
    if day is not None and not DAY.match(day):
        raise SystemExit(f"not a day: {day} (YYYY-MM-DD)")
    raw = client.download(box, f"{STATE}/{day or 'latest'}.json", timeout=60)
    return json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)


def summary(r: Mapping[str, Any]) -> str:
    lines = [f"House receipts for {r.get('day')} (written {r.get('written_at')})"]
    h = r.get("health") or {}
    if h:
        live = h.get("options_live") or {}
        lines.append(f"  health {h.get('at')}: release {h.get('release')}, real money {h.get('real_money')}, failures "
                     f"{len(h.get('failures') or [])}, restarts 24h {h.get('restarts_24h')} ({h.get('restarts_24h_in_session')} in session), "
                     f"live {live.get('state')} blocked {live.get('blocked') or 'no'}")
        ops = h.get("ops") or {}
        if ops:
            lines.append(f"  jobs now: running {ops.get('running') or '-'}, late {ops.get('late') or '-'}, "
                         f"failed {ops.get('failed') or '-'}, missed {ops.get('missed') or '-'}")
    by = r.get("jobs_by_status") or {}
    lines.append("  jobs today: " + (", ".join(f"{k} {v}" for k, v in sorted(by.items())) or "none"))
    for job in r.get("jobs") or []:
        what = job.get("error") or ""
        s = job.get("summary") or {}
        if not what and isinstance(s, Mapping):
            what = s.get("why") or ", ".join(f"{k} {s[k]}" for k in list(s)[:4] if not isinstance(s[k], (dict, list)))
        lines.append(f"    {job.get('due_at')} {job.get('job'):<11} {job.get('status'):<8} {str(what)[:110]}")
    deploys = r.get("deploys") or []
    verdicts = [d for d in deploys if d.get("stage") == "verdict"]
    lines.append(f"  deploys today: {len(deploys)} rows, verdicts: "
                 + (", ".join(f"{d.get('release')} {d.get('verdict')}" for d in verdicts) or "none"))
    spend = r.get("spend") or {}
    if spend and not spend.get("error"):
        lines.append("  spend today: " + ", ".join(f"{k} ${v.get('usd', 0):.2f}" for k, v in sorted(spend.items())))
    elif spend:
        lines.append(f"  spend today: {spend.get('error')}")
    e = r.get("economics") or {}
    if e:
        lines.append(f"  economics at {e.get('cutoff')}: realized {e.get('realized_options_pnl_usd')}, costs {e.get('total_costs_usd')}, "
                     f"Net {e.get('net_usd')}, p30 {(e.get('p30') or {}).get('usd')}")
    b = r.get("budget")
    if isinstance(b, Mapping):
        lines.append(f"  budget: {b.get('state') or b.get('why') or '-'}; direction {b.get('direction') or '-'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("day", nargs="?", help="a UTC day YYYY-MM-DD (default: latest.json)")
    parser.add_argument("--box", help="the House box id (default: .data/ltcm/box.json)")
    parser.add_argument("--json", action="store_true", help="print the whole file as JSON")
    args = parser.parse_args(argv)
    box = args.box or recorded_box()
    if not box:
        raise SystemExit(f"no box: pass --box or record one in {BOX_RECORD}")
    from league.sailbox import SailboxClient

    receipts = fetch(SailboxClient(), box, args.day)
    print(json.dumps(receipts, indent=1, sort_keys=True) if args.json else summary(receipts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
