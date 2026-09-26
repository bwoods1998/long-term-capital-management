"""The venues the House trades on, all through the Cloudflare gateway.

The House holds one gateway token and no venue key. `alpaca-paper` is the same Alpaca adapter as
`alpaca`: the gateway signs it with the paper key pair and sends it to the paper host, never
meters it and lets it through the kill switch, because no money is behind it.
"""

from __future__ import annotations

import re
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any, Callable, Iterable, Mapping

from league.adapters import AlpacaCredentials, GatewaySigner, VenueClient
from league.adapters.alpaca import DEFAULT_FEED, AlpacaBroker
from league.broker import Instrument
from league.data import market_open_at

#: Books that hold the owner's money. Every other book is practice.
REAL_VENUES = ("alpaca",)
PAPER_VENUES = ("alpaca-paper",)
GATEWAY_VENUES = REAL_VENUES + PAPER_VENUES

CENT = Decimal("0.01")
#: A US stock under $1 is quoted to a hundredth of a cent (Reg NMS rule 612); at $1 and above, to the cent.
SUB_PENNY = Decimal("0.0001")


def gateway_broker(venue: str, *, gateway_url: str, token: str, transport: Any = None, clock: Any = None,
                   feed: str = DEFAULT_FEED, option_feed: str = "indicative"):
    """The adapter for `venue`, speaking only to the gateway."""
    if venue not in GATEWAY_VENUES:
        raise ValueError(f"the gateway does not serve {venue!r}")
    signer = GatewaySigner(token)
    client = VenueClient(transport, gateway_url=gateway_url, gateway=signer, venue=venue)
    if option_feed not in ('indicative', 'opra'):
        raise ValueError('option_feed must be indicative or opra')
    # The credential is a placeholder: the gateway drops the APCA headers and signs with its own.
    return AlpacaBroker(AlpacaCredentials("gateway", "gateway", paper=False), client=client, venue=venue,
                        feed=feed, option_feed=option_feed)


def family_of(venue: str) -> str:
    """Which fee model and rules a book uses: a paper or shadow book uses its real venue's."""
    if venue not in GATEWAY_VENUES and venue not in ("options-shadow", "alpaca-sim"):
        raise ValueError(f"unsupported options venue {venue!r}")
    return "alpaca"


def market_hours(instrument: Instrument, now: str) -> bool | None:
    """True or False for instruments with a trading day; None for markets that never close."""
    if instrument.asset_class in ("equity", "option"):
        return market_open_at(now)
    return None


def min_order_usd(instrument: Instrument) -> Decimal | None:
    """Options use whole contracts and structure maximum loss, not a dollar-notional minimum."""
    return None


def price_increment(instrument: Instrument, price: Decimal | None, *, asset: Mapping[str, Any] | None = None,
                    bands: Iterable[Mapping[str, Decimal]] | None = None) -> Decimal | None:
    """The share price grid; option classes use their exchange-specific tick in the live path."""
    if instrument.asset_class == "equity":
        return None if price is None else (CENT if price >= 1 else SUB_PENNY)
    return None


def snap_limit(instrument: Instrument, side: str, price: Decimal | None, increment: Decimal | None) -> Decimal | None:
    """A limit price put on the venue's grid without ever becoming more aggressive: a buy snaps DOWN
    and a sell UP to a whole number of increments. Unchanged when the increment is unknown, or when
    the snap would leave the price's range -- zero or below, because
    no snap in the permitted direction can fix that; the venue refuses it and says why."""
    if price is None or increment is None or increment <= 0:
        return price
    ticks = (price / increment).to_integral_value(rounding=ROUND_FLOOR if side == "buy" else ROUND_CEILING)
    snapped = ticks * increment
    if snapped <= 0 or snapped == price:
        return price
    return snapped


def instrument_for(venue: str, spec: dict[str, Any]) -> Instrument:
    """Parse an OCC option contract or an underlying share held after assignment."""
    family_of(venue)
    occ = str(spec.get("occ") or "").strip().upper()
    if not occ and not (spec.get("expiry") or spec.get("strike")):
        # The chain's rows carry the OCC code in `symbol` too, and strategies pass it back that way:
        # read as a ticker, every options entry was refused as outside the specialty (Sept 21, 2026).
        named = str(spec.get("symbol") or "").strip().upper()
        if re.fullmatch(r"[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}", named):
            occ = named
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
        raise ValueError("crypto instruments are outside the options House")
    return Instrument("equity", symbol, venue)
