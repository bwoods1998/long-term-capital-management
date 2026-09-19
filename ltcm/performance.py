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

    alpaca = brokers.get("alpaca")
    if alpaca is not None:
        flows.extend(alpaca_flows(alpaca, start))
    return flows


#: Alpaca account activities that move the owner's own money in or out of the account. `net_amount`
#: is signed by the venue, so a withdrawal already arrives negative.
ALPACA_FUNDING = {"CSD", "CSW", "JNLC", "JNLS", "ACATC", "ACATS", "CSR", "WIRE"}
#: Activities that are the account earning or paying, which is performance, not funding: dividends
#: and their adjustments, interest, fees, corporate actions and anything else that arises from
#: what the account holds rather than from the owner moving money.
ALPACA_RETURNS = {
    "FILL", "DIV", "DIVCGL", "DIVCGS", "DIVFEE", "DIVFT", "DIVNRA", "DIVROC", "DIVTW", "DIVTXEX",
    "INT", "INTNRA", "INTTW", "FEE", "CFEE", "MA", "NC", "OPASN", "OPCA", "OPCSH", "OPEXC",
    "OPEXP", "OPTRD", "PTC", "PTR", "REORG", "SC", "SSO", "SSP", "SWP", "MISC", "TRANS",
}


def alpaca_flows(broker, start):
    """External cash flows on Alpaca since `start`, as `(venue, timestamp, signed USD)`.

    Reads every account activity rather than a chosen few types, so an activity this runtime
    has never seen raises instead of being counted, silently, as profit. Trades and the
    account's own earnings are skipped; only the owner's own money moving in or out is a flow.
    """
    found = []
    page_token, seen = None, set()
    for _ in range(100):
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        rows = broker._call("GET", "/v2/account/activities", params=params, what="performance funding")
        if not isinstance(rows, list):
            raise ValueError("Unreadable activity history")
        # An activity is counted once, by its own id: a page that repeats (a cursor that does
        # not advance) ends the walk instead of counting its rows twice.
        fresh = []
        for row in rows:
            identifier = row.get("id")
            if not isinstance(identifier, str) or not identifier:
                raise ValueError("Activity without an identifier")
            if identifier not in seen:
                seen.add(identifier)
                fresh.append(row)
        if not fresh:
            return found
        for row in fresh:
            kind = str(row.get("activity_type") or "")
            if kind in ALPACA_RETURNS:
                continue
            if kind not in ALPACA_FUNDING:
                raise ValueError("Unclassified account activity")
            # When the money actually moved, not when it books. An instant ACH deposit made on
            # Saturday carries `date` of the Monday it settles, while the cash is in the balance
            # at once; reading `date` counted the owner's own opening deposit as a flow that
            # arrived after the baseline it was already inside (Sept 19, 2026).
            when_text = row.get("transaction_time") or row.get("created_at") or row.get("date")
            if not when_text:
                raise ValueError("Activity without a time")
            when = stamp(when_text if "T" in str(when_text) else f"{when_text}T00:00:00Z")
            if when <= start:
                continue
            if str(row.get("status") or "executed") not in {"executed", "complete", "completed"}:
                raise ValueError("Unsettled funding")
            found.append(("alpaca", when, amount(row["net_amount"])))
        page_token = rows[-1].get("id")
        if not page_token:
            return found
    raise ValueError("Incomplete funding history")


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
        # Every venue the floor trades has to answer, whichever those are: a profit figure that
        # silently drops an account is worse than no figure (Sept 19, 2026, when Alpaca joined).
        wanted = {str(v) for v in (self.config.get("venues") or ("kalshi", "coinbase"))}
        complete = set(venues) == wanted and not any(row.get("stale") for row in venues.values())
        ready = complete and flows is not None and verified and 0 <= stamp(at) - stamp(verified) <= 600
        net = sum((value for venue, when, value in (flows or [])
                   if venue in venues and when <= stamp(venues[venue]["as_of"])), Decimal(0))
        return {"start_at": self.config["start_at"], "start_equity": str(amount(self.config["start_equity"])),
                "net_flows": str(net) if ready else None,
                "verified_at": verified if ready else None}
