"""The standing grant's House job (LTCM v3, WP4; GOAL.md D5): hourly and at House start.

The owner used to run `scripts/live_trading.py --ratify` after every deploy that moved the money digest and after
every deposit. This job runs `LiveGrant.standing` (`league/live_trading.py`) instead, which ratifies the grant in
force in exactly those two cases and refuses anything else (see there). It never creates, enables or revokes a grant,
never moves the ceiling or a money rule, and sends no order: it reads the Brokerage Account's funding activities and,
only when there is something to answer, its equity, both through the gateway.

The receipt carries the grant's policy hash before and after, the triggers, the verdict and why, and no figure of
the account. A refusal while a trigger is pending is `failed` (and a warning alert when the runner hands one in): with
a moved digest, new real entries stay held until the owner ratifies. Protected: `ci.FORBIDDEN` lists this file.

`run(ctx)` reads from `ctx` (a mapping or an object; anything missing has a default): `root` (the House's state
root; or `state_root`, or `house.root`), `base` (the release base holding `current` and `deploys.jsonl`; default the
root's parent), `config`, `clock`, `alert(level, text)`, and the seams `read_equity()`, `read_funding(after_iso)`,
`release_id` (a release id; a string `release` is accepted too, but the runner's `Context.release` is a directory and
is ignored: the id is then read from `<base>/current`), `deploy_rows`.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Mapping

NAME = "grant"
#: Hourly, and once at every House start (the registry's schedule; `league/ops`).
EVERY_SECONDS = 3600
AT_START = True
#: Funding types the activities endpoint refuses as a filter (`league/live/step.py` `UNQUERYABLE_FUNDING`): naming
#: one fails the whole read. A deposit of such a type is answered at the next deposit, or by the owner's `--ratify`.
UNQUERYABLE_FUNDING = frozenset({"WIRE"})
#: The activities are asked from this long before the pin (the venue's `after` may read a booking date); which ones
#: landed after the pin is decided here on the time the money moved (`live_trading.deposits_after`).
LOOKBACK_SECONDS = 3 * 86400
#: The deploy record is read from its tail: rows before the pin never matter.
DEPLOYS_TAIL_BYTES = 4 << 20


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    value = ctx.get(name) if isinstance(ctx, Mapping) else getattr(ctx, name, None)
    return default if value is None else value


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(max(0.0, float(epoch))))


def deploy_rows(base: Path) -> list[dict[str, Any]]:
    """`<base>/deploys.jsonl`, its tail, as rows (a torn or foreign line is skipped; a missing file is no rows)."""
    path = base / "deploys.jsonl"
    try:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - DEPLOYS_TAIL_BYTES))
            lines = handle.read().decode("utf-8", "replace").splitlines()
            if size > DEPLOYS_TAIL_BYTES:
                lines = lines[1:]  # the first line of a tail may be cut
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def running_release(base: Path) -> str | None:
    """The release `<base>/current` points at (`league/watchdog.py` `Releases.current`), or None."""
    from ..watchdog import RELEASE_ID

    try:
        name = Path(os.readlink(base / "current")).name
    except OSError:
        return None
    return name if RELEASE_ID.match(name) and (base / "releases" / name).is_dir() else None


def _gateway_funding(config: Mapping[str, Any]) -> Callable[[str], list[dict[str, Any]]]:
    """The Brokerage Account's funding activities after a time, through the gateway (a read: no order)."""
    from ltcm.adapters import GatewaySigner, VenueClient
    from ltcm.performance import ALPACA_FUNDING

    from ..live.venue import Account
    from ..live_trading import VENUE
    from ..service import load_env, secret

    load_env()
    client = VenueClient(None, gateway_url=config["gateway_url"], gateway=GatewaySigner(secret("GATEWAY_TOKEN")), venue=VENUE)
    account = Account(client, venue=VENUE)
    types = sorted(set(ALPACA_FUNDING) - UNQUERYABLE_FUNDING)
    return lambda after: account.activities(types, after=after)


def run(ctx: Any) -> dict[str, Any]:
    from ..live_trading import STORE, LiveGrant, ceiling, deposits_after, read_equity

    house = _get(ctx, "house")
    root = _get(ctx, "root") or _get(ctx, "state_root") or (getattr(house, "root", None) if house is not None else None)
    if root is None:
        return {"status": "failed", "action": "none", "error": "no state root"}
    root = Path(root)
    base = Path(_get(ctx, "base") or root.parent)
    clock: Callable[[], float] = _get(ctx, "clock", time.time)
    alert = _get(ctx, "alert")
    receipt: dict[str, Any] = {"status": "ok", "action": "none", "grant": None, "triggers": [], "why": "",
                               "before": None, "after": None}

    def failed(error: str) -> dict[str, Any]:
        receipt.update(status="failed", error=error[:300])
        if callable(alert):
            try:
                alert("warning", f"standing grant: {error[:300]}")
            except Exception:  # noqa: BLE001 - the receipt says it anyway
                pass
        return receipt

    if not (root / STORE).exists():
        receipt["why"] = "no grant store: nothing to keep"
        return receipt
    grant = LiveGrant(root / STORE, clock=clock)
    try:
        due = grant.standing_due()
        receipt.update(grant=due["grant"], before=due["policy_hash"], after=due["policy_hash"])
        if due["grant"] is None:
            receipt["why"] = "the grant is revoked; a revoked grant is never ratified" if due["revoked"] else "no grant to keep"
            return receipt
        try:
            config = _get(ctx, "config")
            if config is None:
                from ..service import load_config

                config = load_config()
            top = ceiling(config)
        except Exception as exc:  # noqa: BLE001
            return failed(f"the owner's ceiling cannot be read ({type(exc).__name__}: {str(exc)[:160]})")
        funding: list[Any] = []
        try:
            read_funding = _get(ctx, "read_funding") or _gateway_funding(config)
            funding = list(read_funding(_iso(due["since"] - LOOKBACK_SECONDS)) or [])
        except Exception as exc:  # noqa: BLE001 - a moved digest is still answered; a deposit waits for a reading
            if not due["digest_moved"]:
                return failed(f"the account's funding cannot be read ({type(exc).__name__}: {str(exc)[:160]})")
            receipt["funding_unread"] = f"{type(exc).__name__}"
        landed = deposits_after(funding, due["since"])
        receipt["triggers"] = (["digest"] if due["digest_moved"] else []) + (["deposit"] if landed else [])
        if not receipt["triggers"]:
            receipt["why"] = "the grant holds on the money digest and no deposit landed since it was pinned"
            return receipt
        try:
            equity = (_get(ctx, "read_equity") or (lambda: read_equity(config)))()
        except Exception as exc:  # noqa: BLE001
            return failed(f"the account's equity cannot be read ({type(exc).__name__}: {str(exc)[:160]})")
        # The release id `<base>/current` names. The runner's `Context.release` is the release DIRECTORY (a Path, always
        # truthy), never an id: only a string handed in as `release_id` (or `release`, a test seam) stands in for it.
        seam = _get(ctx, "release_id") or _get(ctx, "release")
        release = seam if isinstance(seam, str) else running_release(base)
        rows = _get(ctx, "deploy_rows")
        rows = deploy_rows(base) if rows is None else list(rows)
        out = grant.standing(clock(), equity, release, rows, funding=funding, ceiling_usd=top)
        receipt.update({key: out[key] for key in ("action", "grant", "triggers", "why", "before", "after", "release", "digest")})
        if out["action"] == "refused":
            return failed(str(out["why"]).removeprefix("standing: "))
        return receipt
    finally:
        grant.close()
