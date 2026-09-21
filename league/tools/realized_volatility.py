"""Realized volatility from already-available closing prices.

Usage in a strategy::

    from tools.realized_volatility import realized_volatility
    # window_bars must already be selected for this market's underlier,
    # observation window, and the information available at ctx['now'].
    vol = realized_volatility([bar['c'] for bar in window_bars])

For prices p[0], ..., p[n], return
    sqrt(sum((log(p[i]) - log(p[i - 1])) ** 2 for i in 1..n)).
This is unannualized realized volatility, not the demeaned sample standard
 deviation of returns. The result is dimensionless: 0.01 is approximately
1% log-return volatility over the supplied observations. No drift removal,
annualization, missing-bar interpolation, or time scaling is performed.

The caller owns point-in-time selection and market-to-underlier mapping.
For an interval starting at T, supply a price at T and subsequent eligible
closes through the earlier of the window end and the current decision time.
Do not include a return crossing the start boundary or a bar not yet closed
and available. Respect the feed's timestamp convention: a bar's timestamp
may identify its opening time rather than its availability time. If exact
boundary observations are absent, the result covers only the supplied
sample, not necessarily the entire requested interval.

This helper deliberately accepts no timestamps and cannot verify ordering,
coverage, freshness, settlement-source equivalence, or window completeness.
Gaps and coarse sampling can miss intrabar variation. A 5Min sample does
not become a 1Min estimate by scaling this result, and a partial-window
estimate is not a forecast of full-window or settlement volatility.

At least two closes are required (one return). Insufficient observations
raise ValueError rather than falsely reporting zero volatility. Closes must
be non-boolean int/float values representable as finite, positive floats;
invalid prices also raise ValueError. Other numeric types and numeric
strings are not accepted. Input order is preserved and inputs are not
mutated. An iterable of closes is consumed once. Runtime and temporary
storage are linear in the number of closes.
"""

import math


def realized_volatility(closes):
    """Return unannualized sqrt(sum of squared log returns); see module docs."""
    log_prices = []
    for price in closes:
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError('closes must contain non-boolean int/float prices')
        try:
            value = float(price)
        except OverflowError:
            raise ValueError('closes must be representable as finite positive floats')
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError('closes must contain finite positive prices')
        log_prices.append(math.log(value))

    if len(log_prices) < 2:
        raise ValueError('at least two closes are required')

    # Subtract logs instead of forming a ratio that could overflow/underflow.
    squared_returns = (
        (right - left) ** 2
        for left, right in zip(log_prices, log_prices[1:])
    )
    return math.sqrt(math.fsum(squared_returns))
