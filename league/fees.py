"""What a fill costs, per venue, as the venue actually charges it.

Measured, not assumed:

- **Alpaca crypto** (paper, Sept 19, 2026): a market buy of 0.0002 BTC left a position of
  0.0001995: the 0.25% taker fee came out of the asset bought, not out of cash. The sell of
  0.0001995 at 80,967.80 raised cash by $16.11, not $16.15: the fee on a sell comes out of the
  proceeds. The adapter reports a fee of zero on both, so the book applies this model.
- **Alpaca equities and options**: no commission. The regulatory pennies on a sell are below the
  model and are absorbed by reconciliation as dust. Except an option fill's OCC clearing fee
  (`option_clearing`, which the House sets on every Alpaca book). Measured Sept 21-24, 2026 on the
  paper account: one "OCC Clearing Fee" activity for each of the 46 option trades of Sept 21-23,
  $0.03 for one contract and $0.05 for two ($0.025 a contract, rounded up to the cent a fill), taken
  from cash at the fill ($0.03 on a one-contract buy; $0.02 on a sale, the last cent in the next
  morning's batch) but listed as a FEE activity only the next morning, when the book had already
  frozen on it or booked it as dust. It is the agent's cost, so the fill pays it. The rest of an
  option day's fees (ORF on every contract, TAF and the regulatory fee on sales) are summed and taken
  in the overnight batch, and `Book._book_venue_fees` books them to the House when that cash moves.
  The REAL account (H4, Sept 25, 2026, from its first two fills of Sept 24): the OCC fee ($0.03 a
  contract) left the cash at the fill and was listed 11 s and 8 s later; the ORF and CAT cents left
  the cash at the fill too and were listed only at 20:35Z and 00:31Z, which `Book._explain_real_cents`
  books to the House row as dust under `allocator.real_book_dust_usd`.
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
#: The OCC clearing fee on an Alpaca option fill, a contract (rounded up to the cent a fill).
ALPACA_OPTION_CLEARING = Decimal("0.025")


@dataclass(frozen=True)
class Charge:
    """A fill's cost: dollars taken from cash, and units taken from the asset received."""

    usd: Decimal = ZERO
    quantity: Decimal = ZERO


class Fees:
    """The fee model of one venue family (`alpaca` or `kalshi`)."""

    def __init__(self, family: str, *, option_clearing: bool = False):
        if family not in ("alpaca", "kalshi"):
            raise ValueError(f"no fee model for {family!r}")
        self.family = family
        #: Charge an Alpaca option fill the OCC clearing fee the venue takes at the fill (every Alpaca book since H4).
        self.option_clearing = bool(option_clearing) and family == "alpaca"
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
        if instrument.asset_class == "option" and self.option_clearing and quantity > 0:
            return Charge(usd=(quantity * ALPACA_OPTION_CLEARING).quantize(CENT, rounding=ROUND_CEILING))
        return Charge()


def received(quantity: Decimal, charge: Charge) -> Decimal:
    """Units that actually reach the position after an in-kind fee."""
    return (money(quantity) - charge.quantity).quantize(QTY_PLACES, rounding=ROUND_DOWN)
