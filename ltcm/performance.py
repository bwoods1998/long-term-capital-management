"""Owner-account performance, deliberately independent of virtual desk allocations.

Funding reads run off the trading/checkpoint path. Unknown transfer types, incomplete
pagination or an unavailable venue make profit unavailable, never silently zero flows.
No transaction identifiers or private funding records enter the public checkpoint.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qsl, urlsplit


def stamp(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()


def amount(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Invalid funding amount")
    return result


def funding_flows(brokers, start_at):
    """Return (venue, timestamp, signed USD) external flows since the audited mark."""
    start = stamp(start_at)
    flows = []
    kalshi = brokers["kalshi"]
    for resource, sign in (("deposits", 1), ("withdrawals", -1)):
        cursor, seen = None, set()
        for _ in range(100):
            page = kalshi._call("GET", "/portfolio/" + resource,
                                params={"limit": 100, "cursor": cursor}, what="performance funding")
            for row in page[resource]:
                when = row.get("finalized_ts") or row["created_ts"]
                if when <= start or row["status"] in {"failed", "canceled", "cancelled"}:
                    continue
                if row["status"] != "applied":
                    raise ValueError("Unsettled funding")
                flows.append(("kalshi", float(when), sign * amount(row["amount_cents"]) / 100))
            cursor = page.get("cursor")
            if not cursor:
                break
            if cursor in seen:
                raise ValueError("Repeated funding cursor")
            seen.add(cursor)
        else:
            raise ValueError("Incomplete funding history")

    coinbase = brokers["coinbase"]

    def pages(path):
        next_path, seen = path + "?limit=100", set()
        for _ in range(100):
            if next_path in seen:
                raise ValueError("Repeated funding cursor")
            seen.add(next_path)
            parsed = urlsplit(next_path)
            # Follow only a relative pagination link for this exact collection.
            if parsed.scheme or parsed.netloc or parsed.path != path:
                raise ValueError("Unexpected funding pagination")
            page = coinbase._call("GET", parsed.path, params=dict(parse_qsl(parsed.query)), what="performance funding")
            yield from page["data"]
            next_path = page.get("pagination", {}).get("next_uri")
            if not next_path:
                return
        raise ValueError("Incomplete funding history")

    for account in pages("/v2/accounts"):
        account_id = account["id"]
        if not isinstance(account_id, str) or not all(c.isalnum() or c == "-" for c in account_id):
            raise ValueError("Invalid account identifier")
        for row in pages(f"/v2/accounts/{account_id}/transactions"):
            when = stamp(row["created_at"])
            if when <= start or row["status"] in {"failed", "canceled", "cancelled"}:
                continue
            kind = row["type"]
            # Fills are exchanges of assets inside the portfolio, not owner funding.
            # Derivatives settlements move cash between the spot and futures
            # balances of the same portfolio (daily perp mark-to-market).
            if kind in {"advanced_trade_fill", "derivatives_settlement"}:
                continue
            if row["status"] != "completed" or kind not in {"fiat_deposit", "fiat_withdrawal", "send"}:
                raise ValueError("Unclassified account transaction")
            native = row["native_amount"]
            if native["currency"] != "USD":
                raise ValueError("Funding has no USD valuation")
            value = amount(native["amount"])
            units = amount(row["amount"]["amount"])
            if (value == 0 and units != 0) or (value * units < 0):
                raise ValueError("Ambiguous funding valuation")
            if kind == "fiat_deposit" and value < 0 or kind == "fiat_withdrawal" and value > 0:
                raise ValueError("Unexpected funding direction")
            flows.append(("coinbase", when, value))
    return flows


class AccountPerformance:
    """Small, read-only background cache. Never changes risk, rewards or trading."""

    def __init__(self, config, brokers, clock=time.time):
        self.config, self.brokers, self.clock = dict(config), brokers, clock
        self.lock = threading.Lock()
        self.busy, self.attempted = False, float("-inf")
        self.verified_at, self.flows = None, None

    def _refresh(self, at):
        try:
            flows = funding_flows(self.brokers, self.config["start_at"])
        except Exception:
            # A failed refresh invalidates old flow assumptions immediately.
            flows = None
        with self.lock:
            self.flows = flows
            self.verified_at = at if flows is not None else None
            self.busy = False

    def read(self, account, at):
        now = self.clock()
        with self.lock:
            if not self.busy and now - self.attempted >= 300:
                self.busy, self.attempted = True, now
                threading.Thread(target=self._refresh, args=(at,), daemon=True,
                                 name="account-funding").start()
            flows, verified = self.flows, self.verified_at
        venues = {row["venue"]: row for row in account.get("venues", [])}
        complete = set(venues) == {"kalshi", "coinbase"} and not any(row.get("stale") for row in venues.values())
        ready = complete and flows is not None and verified and 0 <= stamp(at) - stamp(verified) <= 600
        net = sum((value for venue, when, value in (flows or [])
                   if venue in venues and when <= stamp(venues[venue]["as_of"])), Decimal(0))
        return {"start_at": self.config["start_at"], "start_equity": str(amount(self.config["start_equity"])),
                "net_flows": str(net) if ready else None,
                "verified_at": verified if ready else None}
