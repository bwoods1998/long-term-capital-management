"""The venues the House trades on, all through the Cloudflare gateway.

The House holds one gateway token and no venue key. `alpaca-paper` is the same Alpaca adapter as
`alpaca`: the gateway signs it with the paper key pair and sends it to the paper host, never
meters it and lets it through the kill switch, because no money is behind it.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from ltcm.adapters import AlpacaCredentials, GatewaySigner, KalshiCredentials, VenueClient
from ltcm.adapters.alpaca import DEFAULT_FEED, AlpacaBroker
from ltcm.adapters.kalshi import KalshiBroker
from ltcm.broker import Instrument
from ltcm.data import market_open_at

#: Books that hold the owner's money. Every other book is practice.
REAL_VENUES = ("kalshi", "alpaca")
PAPER_VENUES = ("alpaca-paper",)
GATEWAY_VENUES = REAL_VENUES + PAPER_VENUES


def gateway_broker(venue: str, *, gateway_url: str, token: str, transport: Any = None, clock: Any = None,
                   feed: str = DEFAULT_FEED, option_feed: str = "indicative"):
    """The adapter for `venue`, speaking only to the gateway."""
    if venue not in GATEWAY_VENUES:
        raise ValueError(f"the gateway does not serve {venue!r}")
    signer = GatewaySigner(token)
    client = VenueClient(transport, gateway_url=gateway_url, gateway=signer, venue=venue)
    if venue == "kalshi":
        return KalshiBroker(KalshiCredentials("gateway", signer), client=client, clock=clock)
    if option_feed not in ('indicative', 'opra'):
        raise ValueError('option_feed must be indicative or opra')
    # The credential is a placeholder: the gateway drops the APCA headers and signs with its own.
    return AlpacaBroker(AlpacaCredentials("gateway", "gateway", paper=False), client=client, venue=venue,
                        feed=feed, option_feed=option_feed)


def family_of(venue: str) -> str:
    """Which fee model and rules a book uses: a paper or shadow book uses its real venue's."""
    return "kalshi" if venue.startswith("kalshi") else "alpaca"


def market_hours(instrument: Instrument, now: str) -> bool | None:
    """True or False for instruments with a trading day; None for markets that never close."""
    if instrument.asset_class in ("equity", "option"):
        return market_open_at(now)
    return None


def instrument_for(venue: str, spec: dict[str, Any]) -> Instrument:
    """An agent names what it wants to trade in plain data; this is the only parser of it.

    `{"symbol": "BTC/USD"}` crypto, `{"symbol": "SPY"}` equity,
    `{"symbol": "SPY", "expiry": "2026-10-16", "strike": "650", "right": "call"}` or `{"occ": "SPY261016C00650000"}` option,
    `{"market": "KXBTCD-...", "leg": "yes"}` a Kalshi contract.
    """
    if family_of(venue) == "kalshi":
        ticker = str(spec.get("market") or spec.get("symbol") or "").strip().upper()
        leg = str(spec.get("leg") or spec.get("right") or "yes").strip().lower()
        if not ticker or leg not in ("yes", "no"):
            raise ValueError("a Kalshi instrument is {market, leg: yes|no}")
        return Instrument("event", ticker, venue, market_id=ticker, right=leg)
    occ = str(spec.get("occ") or "").strip().upper()
    if occ:
        # The chain names a contract by its OCC symbol (`F260925C00013000`): the shortest way to say which.
        if not re.fullmatch(r"[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}", occ):
            raise ValueError(f"not an OCC option symbol: {occ!r}")
        from decimal import Decimal

        return Instrument("option", occ[:-15], venue, multiplier=100, expiry=f"20{occ[-15:-13]}-{occ[-13:-11]}-{occ[-11:-9]}",
                          strike=Decimal(int(occ[-8:])) / 1000, right="call" if occ[-9] == "C" else "put")
    symbol = str(spec.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("an Alpaca instrument needs a symbol")
    if spec.get("expiry") or spec.get("strike"):
        right = str(spec.get("right") or "").lower()
        return Instrument("option", symbol, venue, multiplier=100, expiry=str(spec.get("expiry")), strike=spec.get("strike"), right=right)
    if "/" in symbol or symbol.endswith("-USD"):
        pair = symbol.replace("-", "/")
        return Instrument("crypto", pair.replace("/", "-"), venue, market_id=pair)
    return Instrument("equity", symbol, venue)
