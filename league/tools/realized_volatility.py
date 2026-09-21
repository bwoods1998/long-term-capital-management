"""Causal, unannualized realized volatility from supplied closed spot bars.

Use from tools.realized_volatility import realized_volatility.

Example, only when the source stamps bars at their START:
    result = realized_volatility(
        ctx['observed']['bars']['BTC/USD'],
        window_start, ctx['now'], bar_seconds=300, timestamp_at='start')
    if result['complete']:
        sigma = result['volatility']

window_start and as_of are timezone-aware ISO strings. window_start is a
price-observation baseline, not the timestamp of the first return. The caller
must verify the market's underlier and observation window; do not assume that
close_time minus fifteen minutes always identifies its settlement window.

bar_seconds is a positive integer describing the ACTUAL input resolution.
timestamp_at must explicitly be 'start' or 'end'. For start-stamped bars, t plus
bar_seconds is the close time; for end-stamped bars, t is the close time.
Only closes from window_start through as_of are considered. They must lie on
the grid window_start + k * bar_seconds and be strictly chronological.
Rows outside that interval are ignored, including their close values.

Output is a JSON-compatible dict:
  expected_returns: whole bar intervals elapsed since window_start;
  n_returns: observed adjacent-grid returns (never bridged across a gap);
  complete: at least one return and every required close is present;
  variance: sum of squared log returns, or None if incomplete;
  volatility: sqrt(variance), or None if incomplete.

Completeness refers to the whole-bar PREFIX through the last grid point at or
before as_of. Any fractional last interval is excluded. Fifteen one-minute
returns need sixteen closes, including the baseline. Missing observations are
not zero volatility. Constant observed prices do produce zero volatility.

This is not demeaned sample variance, annualized volatility, remaining-window
volatility, an official settlement statistic, or a price forecast. Coarse bars
cannot reveal finer realized variation. No interpolation or extrapolation is
performed. Only pass rows actually available in the decision's ctx: nominal
bar endings cannot establish source publication or receipt delays. Inputs are
not mutated; runtime and storage are linear in the supplied number of bars.
"""

from datetime import datetime, timedelta, timezone
import math


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamps must be timezone-aware ISO strings')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('timestamps must include a timezone')
    return result.astimezone(timezone.utc)


def realized_volatility(bars, window_start, as_of, bar_seconds, timestamp_at):
    """Compute squared-log-return variation on a complete closed-bar prefix."""
    if isinstance(bar_seconds, bool) or not isinstance(bar_seconds, int):
        raise ValueError('bar_seconds must be a positive integer')
    if bar_seconds <= 0:
        raise ValueError('bar_seconds must be a positive integer')
    if timestamp_at not in ('start', 'end'):
        raise ValueError("timestamp_at must be 'start' or 'end'")
    try:
        step = timedelta(seconds=bar_seconds)
    except OverflowError:
        raise ValueError('bar_seconds is too large')
    start = _timestamp(window_start)
    cutoff = _timestamp(as_of)
    if cutoff < start:
        raise ValueError('as_of must not precede window_start')
    expected = (cutoff - start) // step
    zero = timedelta(0)
    shift = step if timestamp_at == 'start' else zero
    prices = {}
    previous_index = -1
    for bar in bars:
        end = _timestamp(bar['t']) + shift
        if end < start or end > cutoff:
            continue
        offset = end - start
        if offset % step != zero:
            raise ValueError('bar closes must align with the declared window grid')
        index = offset // step
        if index <= previous_index:
            raise ValueError('selected bar closes must be unique and increasing')
        price = bar['c']
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError('close must be a finite positive number')
        try:
            price = float(price)
        except OverflowError:
            raise ValueError('close must be a finite positive number')
        if not math.isfinite(price) or price <= 0:
            raise ValueError('close must be a finite positive number')
        prices[index] = price
        previous_index = index
    returns = [
        math.log(prices[index]) - math.log(prices[index - 1])
        for index in prices
        if index > 0 and index - 1 in prices
    ]
    complete = expected > 0 and len(prices) == expected + 1
    variance = math.fsum(value * value for value in returns) if complete else None
    return {
        'expected_returns': expected,
        'n_returns': len(returns),
        'complete': complete,
        'variance': variance,
        'volatility': math.sqrt(variance) if complete else None,
    }
