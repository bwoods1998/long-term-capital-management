"""What a fill costs, per venue, as the venue actually charges it.

Measured, not assumed:

- **Alpaca crypto** (paper, Sept 19, 2026): a market buy of 0.0002 BTC left a position of
  0.0001995: the 0.25% taker fee came out of the asset bought, not out of cash. The sell of
  0.0001995 at 80,967.80 raised cash by $16.11, not $16.15: the fee on a sell comes out of the
  proceeds. The adapter reports a fee of zero on both, so the book applies this model.
- **Alpaca equities and options**: no commission. The regulatory pennies on a sell are below the
  model and are absorbed by reconciliation as dust.
- **Kalshi**: the venue reports each order's fees, and the book uses the venue's number. This
  model is for the shadow book and for crosses: 0.07 x C x P x (1 - P) times the series
  multiplier, rounded up to $0.0001 per order; a resting fill pays nothing except on the series
  that charge makers (`ltcm/data/kalshi_fees.json`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal

from ltcm.broker import Instrument, money
from ltcm.sim import FeeModel

ZERO = Decimal(0)
CENT = Decimal("0.01")
QTY_PLACES = Decimal("0.000000001")  # Alpaca's nine decimals

ALPACA_CRYPTO_TAKER = Decimal("0.0025")
ALPACA_CRYPTO_MAKER = Decimal("0.0015")


@dataclass(frozen=True)
class Charge:
    """A fill's cost: dollars taken from cash, and units taken from the asset received."""

    usd: Decimal = ZERO
    quantity: Decimal = ZERO


class Fees:
    """The fee model of one venue family (`alpaca` or `kalshi`)."""

    def __init__(self, family: str):
        if family not in ("alpaca", "kalshi"):
            raise ValueError(f"no fee model for {family!r}")
        self.family = family
        self._kalshi = FeeModel.for_venue("kalshi") if family == "kalshi" else None

    def charge(
        self,
        instrument: Instrument,
        side: str,
        quantity: Decimal,
        price: Decimal,
        *,
        liquidity: str = "taker",
        filled_before: Decimal = ZERO,
    ) -> Charge:
        quantity, price = money(quantity), money(price)
        if self.family == "kalshi":
            usd = self._kalshi.fee(
                instrument, side, quantity, price, liquidity=liquidity, filled_before=filled_before
            )
            return Charge(usd=usd)
        if instrument.asset_class == "crypto":
            rate = ALPACA_CRYPTO_MAKER if liquidity == "maker" else ALPACA_CRYPTO_TAKER
            if side == "buy":
                # Rounded up: the venue never rounds a fee in our favour.
                return Charge(quantity=(quantity * rate).quantize(QTY_PLACES, rounding=ROUND_CEILING))
            return Charge(usd=(quantity * price * instrument.multiplier * rate).quantize(CENT, rounding=ROUND_CEILING))
        return Charge()


def received(quantity: Decimal, charge: Charge) -> Decimal:
    """Units that actually reach the position after an in-kind fee."""
    return (money(quantity) - charge.quantity).quantize(QTY_PLACES, rounding=ROUND_DOWN)
