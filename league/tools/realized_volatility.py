"""Sampled, unannualized realized volatility from supplied closing prices.

Usage in a strategy::

    from tools.realized_volatility import realized_volatility
    stats = realized_volatility(bar['c'] for bar in window_bars)
    sigma = stats['realized_volatility']

``window_bars`` must be selected by the caller from supplied bars for the
correct market's underlier and verified observation window. Use chronological
closes available by ctx['now']; understand whether bar timestamps denote
interval starts or ends. This module cannot discover settlement windows,
verify availability timestamps, or select a settlement source.

For closes C[0], ..., C[n], returns are log(C[i] / C[i-1]). Realized variance
is their sum of squares and realized volatility is its square root. Units are
dimensionless log returns over the supplied sample, not percent, per-minute
volatility, annualized volatility, or a forecast. There is no mean subtraction
or degrees-of-freedom adjustment. Fifteen returns need sixteen closes,
including an opening reference; fifteen closes provide fourteen returns.

During an active market, supply only the elapsed window, never its future
final closes. Compare estimates at compatible sampling intervals and elapsed
durations. Gaps contribute an endpoint-to-endpoint return and hide intervening
movement; this function cannot detect them without timestamps. It cannot turn
five-minute bars into one-minute observations, reconstruct quote lead-lag, or
make a sparse estimate equivalent to finely sampled realized volatility.

Result keys: n_closes, n_returns, realized_variance, realized_volatility.
Both estimates are None with fewer than two closes; a sufficiently observed
flat path returns zero. Each price must be a finite, strictly positive Python
int or float (not bool); invalid prices raise ValueError. The input is consumed
once, is not mutated, and is assumed to be in chronological order.
"""

import math


def realized_volatility(closes):
    """Return counts and sampled sum-of-squared-log-return volatility."""
    n_closes = 0
    previous = None
    squared_returns = []

    for price in closes:
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError('closes must contain finite positive numbers')
        try:
            value = float(price)
        except OverflowError:
            raise ValueError('close is outside the finite float range') from None
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError('closes must contain finite positive numbers')

        if previous is not None:
            relative = (value - previous) / previous
            if -0.5 <= relative <= 0.5:
                # Preserve small changes without subtracting two large logs.
                log_return = math.log1p(relative)
            else:
                # Avoid overflow/underflow in the ratio of extreme prices.
                log_return = math.log(value) - math.log(previous)
            squared_returns.append(log_return * log_return)
        previous = value
        n_closes += 1

    variance = math.fsum(squared_returns) if n_closes >= 2 else None
    return {
        'n_closes': n_closes,
        'n_returns': max(0, n_closes - 1),
        'realized_variance': variance,
        'realized_volatility': math.sqrt(variance) if variance is not None else None,
    }
