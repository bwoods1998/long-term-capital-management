"""The venues the House trades on, all through the Cloudflare gateway.

The House holds one gateway token and no venue key. `alpaca-paper` is the same Alpaca adapter as
`alpaca`: the gateway signs it with the paper key pair and sends it to the paper host, never
meters it and lets it through the kill switch, because no money is behind it.
"""

from __future__ import annotations

import re
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any, Callable, Iterable, Mapping

from ltcm.adapters import AlpacaCredentials, GatewaySigner, KalshiCredentials, VenueClient
from ltcm.adapters.alpaca import DEFAULT_FEED, AlpacaBroker
from ltcm.adapters.kalshi import KalshiBroker
from ltcm.broker import Instrument
from ltcm.data import market_open_at

#: Books that hold the owner's money. Every other book is practice.
REAL_VENUES = ("kalshi", "alpaca")
PAPER_VENUES = ("alpaca-paper",)
GATEWAY_VENUES = REAL_VENUES + PAPER_VENUES

#: Alpaca refuses a crypto order worth less than $10: "cost basis must be >= minimal amount of
#: order 10". Measured Sept 20-22, 2026 on the paper book: 55 orders answered HTTP 403 with it in
#: 48 hours, among them requests of exactly $10.00 that the step had floored to $9.9999999.
ALPACA_CRYPTO_MIN_ORDER_USD = Decimal("10")
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


def min_order_usd(instrument: Instrument) -> Decimal | None:
    """The smallest order the venue takes, in dollars, where it is known: $10 for a crypto pair on
    Alpaca, live or paper. None everywhere else: no other venue minimum is documented here."""
    if instrument.asset_class == "crypto" and instrument.venue in ("alpaca", "alpaca-paper"):
        return ALPACA_CRYPTO_MIN_ORDER_USD
    return None


def price_increment(instrument: Instrument, price: Decimal | None, *, asset: Mapping[str, Any] | None = None,
                    bands: Iterable[Mapping[str, Decimal]] | None = None) -> Decimal | None:
    """The venue's price grid at `price`, or None where it is not known.

    - US equities: a cent at $1 and above, a hundredth of a cent below.
    - Crypto: the pair's own `price_increment` from the venue's asset record (`asset`, from
      `AlpacaBroker.asset`), and None without one. Never a cent by default: a cent is a large part of
      a coin's price under a dollar, and rounding to one is the defect the frontier auditor vetoed
      a crypto agent for on Sept 22, 2026.
    - Kalshi: the step of the market's own `price_ranges` band holding the price (`bands`: a cent
      on most markets, finer on some -- `ltcm/adapters/kalshi.py` has markets priced in
      centi-cents), and a cent where the market publishes none, as both Kalshi adapters assume.
    - Options: None. The penny program's tick depends on the class (SPY, QQQ and IWM quote in
      pennies throughout, others in nickels from $3), which the House does not know.
    """
    if instrument.asset_class == "equity":
        return None if price is None else (CENT if price >= 1 else SUB_PENNY)
    if instrument.asset_class == "crypto":
        stated = (asset or {}).get("price_increment")
        return stated if isinstance(stated, Decimal) and stated > 0 else None
    if instrument.asset_class == "event":
        steps = [band["step"] for band in bands or () if band["step"] > 0 and price is not None and band["start"] <= price <= band["end"]]
        return min(steps) if steps else CENT
    return None


def snap_limit(instrument: Instrument, side: str, price: Decimal | None, increment: Decimal | None) -> Decimal | None:
    """A limit price put on the venue's grid without ever becoming more aggressive: a buy snaps DOWN
    and a sell UP to a whole number of increments. Unchanged when the increment is unknown, or when
    the snap would leave the price's range -- zero or below, or an event contract's $1 -- because
    no snap in the permitted direction can fix that; the venue refuses it and says why."""
    if price is None or increment is None or increment <= 0:
        return price
    ticks = (price / increment).to_integral_value(rounding=ROUND_FLOOR if side == "buy" else ROUND_CEILING)
    snapped = ticks * increment
    if snapped <= 0 or (instrument.asset_class == "event" and snapped >= 1) or snapped == price:
        return price
    return snapped


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
        pair = symbol.replace("-", "/")
        return Instrument("crypto", pair.replace("/", "-"), venue, market_id=pair)
    return Instrument("equity", symbol, venue)
