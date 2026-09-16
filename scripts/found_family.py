#!/usr/bin/env python3
"""Found a family by hand, the way the floor does every night at its founding slot.

The floor opens new lines of business itself (`ltcm/founding.py`, the `founding` block in
`ltcm/config.json`). This script runs the same steps on demand, ON THE FLOOR BOX (the deploy
uploads it) or in any checkout that holds `.data/ltcm`:

    cd /workspace && .venv/bin/python scripts/found_family.py --packet      # what the model would read; no model call
    cd /workspace && .venv/bin/python scripts/found_family.py --dry-run     # the proposal and the verdict; nothing written
    cd /workspace && .venv/bin/python scripts/found_family.py --apply       # found it
    cd /workspace && .venv/bin/python scripts/found_family.py --wind-down [--apply]

The model call is keyed `founding:<day>:manual`, so a dry run and the apply after it on the same
day pay once and found the proposal the dry run printed. The floor's caps hold: one founding in
24 hours, the founded-family ceiling, the founding budget, a desk born shadow. A running floor
loads a family founded here at its next roster reload (the hourly seeding pass breeds the new
family's first variant and reloads, or the evening slots). Nothing here prints a credential, and
the venue listings are read without the HTTP cache, so a manual run leaves nothing on the disk
but its model request and, with `--apply`, the desk.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ltcm.data import HttpTransport  # noqa: E402
from ltcm.data.coinbase import CoinbaseMarketData  # noqa: E402
from ltcm.data.kalshi import KalshiMarketData  # noqa: E402
from ltcm.events import EventLog, now_iso  # noqa: E402
from ltcm.evolve import Evolution  # noqa: E402
from ltcm.founding import Founding  # noqa: E402
from ltcm.lab import DEFAULT_CONFIG as LAB_DEFAULTS  # noqa: E402
from ltcm.service import PACKAGE_DIR, default_config  # noqa: E402


def build(root: Path, *, with_provider: bool) -> tuple[Founding, EventLog, dict]:
    config = default_config()
    capital_dir = root / ".data" / "ltcm"
    log = EventLog(capital_dir / "events.sqlite")
    evolution = Evolution(
        log,
        Path(config.get("desks_dir") or (PACKAGE_DIR / "desks")),
        Path(config.get("playbooks_dir") or (root / "playbooks")),
        config={
            **(config.get("evolution") or {}),
            "live_venues": tuple(config.get("live_venues") or ()),
            "committee": dict(config.get("committee") or {}),
        },
    )
    provider = None
    if with_provider:
        from ltcm.provider import Provider

        # The floor's runway sets its own cap at run time; a manual call is bounded by the
        # founding budget and the credit reserve, under the floor's ceiling.
        provider = Provider(
            capital_dir / "provider.sqlite",
            log=log,
            floor_cap_usd_per_day=config.get("floor_cap_max_usd_per_day", "60"),
            reserve_floor_usd=config.get("reserve_floor_usd", "10"),
        )
    transport = HttpTransport(min_interval=0.2)
    lab = dict(config.get("lab") or {})
    founding = Founding(
        log,
        evolution,
        provider=provider,
        config={
            "live_venues": tuple(config.get("live_venues") or ()),
            "hard_limits": {**LAB_DEFAULTS["hard_limits"], **dict(lab.get("hard_limits") or {})},
            **dict(config.get("founding") or {}),
        },
        kalshi=KalshiMarketData(transport),
        coinbase=CoinbaseMarketData(transport),
    )
    return founding, log, config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="ask for a proposal and validate it; write nothing (default)")
    mode.add_argument("--apply", action="store_true", help="found the proposal, or with --wind-down retire the failed families")
    mode.add_argument("--packet", action="store_true", help="print the instructions and the packet; no model call")
    parser.add_argument("--wind-down", action="store_true", help="the wind-down rule instead of a founding")
    parser.add_argument("--root", default=str(ROOT), help="the checkout holding .data/ltcm")
    parser.add_argument("--key", default=None, help="the model request key (default founding:<day>:manual)")
    args = parser.parse_args(argv)

    founding, log, config = build(Path(args.root).resolve(), with_provider=not (args.packet or args.wind_down))
    try:
        at = now_iso()
        day = datetime.now(timezone.utc).astimezone(ZoneInfo(config.get("timezone") or "America/New_York")).date().isoformat()

        if args.wind_down:
            actions = founding.wind_down(at, apply=args.apply)
            print(json.dumps({"apply": args.apply, "founded_families": sorted(founding.founded_families()),
                              "actions": actions}, indent=2, default=str))
            return 0

        refusal = founding.refusal(at)
        if refusal and not args.packet:
            print(f"refused before asking: {refusal}")
            if args.apply or refusal in ("no model provider", "founding is switched off"):
                return 1
        context = founding.prepare(at)
        universe = founding.universe(at, coverage=context["coverage"])
        if universe["errors"]:
            print("listing errors: " + "; ".join(universe["errors"]), file=sys.stderr)
        if not universe["text"]:
            print("no venue listings could be read: no founding")
            return 1
        if args.packet:
            packet = founding.packet(at, context, universe)
            print(str(context["instructions"]) + "\n\n" + packet)
            print(f"\n[instructions {len(str(context['instructions']))} chars, packet {len(packet)} chars, "
                  f"digest {len(universe['text'])} chars]", file=sys.stderr)
            return 0

        key = args.key or f"founding:{day}:manual"
        reply = founding.propose(at, context=context, universe=universe, key=key)
        outcome = founding.settle(reply, at, universe=universe, coverage=context["coverage"], apply=args.apply)
        if outcome.get("status") == "refused" and reply.get("proposal"):
            print(f"refused ({outcome.get('reason')}); asking the model to correct it", file=sys.stderr)
            reply = founding.propose(at, context=context, universe=universe, key=f"{key}:retry",
                                     correction={"text": reply.get("text"), "reason": outcome.get("reason")})
            outcome = founding.settle(reply, at, universe=universe, coverage=context["coverage"], apply=args.apply)
        shown = dict(outcome)
        validated = shown.pop("proposal", None)
        print(json.dumps(shown, indent=2, default=str))
        if validated is not None:
            print(json.dumps({k: validated[k] for k in ("id", "family", "name", "universe", "targets", "venues",
                                                          "asset_classes", "rationale", "manifest")}, indent=2))
            print("\n--- playbook ---\n" + validated["playbook"])
        elif reply.get("proposal") and outcome.get("status") != "founded":
            print(json.dumps(reply["proposal"], indent=2, default=str)[:20_000])
        return 0 if outcome.get("status") in ("valid", "founded") else 1
    finally:
        provider = founding.provider
        if provider is not None and hasattr(provider, "close"):
            provider.close()
        log.close()


if __name__ == "__main__":
    sys.exit(main())
