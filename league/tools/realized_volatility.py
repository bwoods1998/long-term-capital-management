"""Time-bounded realized volatility from bars already available to a strategy.

Agent usage::

    from tools.realized_volatility import window_realized_volatility
    result = window_realized_volatility(
        ctx['observed']['bars']['BTC/USD'],
        start='2026-09-21T12:00:00Z',  # explicit market-window start
        as_of=ctx['now'],
        bar_seconds=300,
    )

Select the underlying and window from known contract terms, not from this
helper. This module supplies no data and does not identify settlement sources.
Use the same bar cadence as NEEDS.bars: 300 seconds for 5Min, 60 for 1Min.
Do not interpolate coarse bars to manufacture finer observations.

By default t denotes a bar's START, so its close is usable only at t plus
bar_seconds. Use timestamp_at='end' only when the source explicitly stamps
bar ends. Timestamps must be timezone-aware ISO strings. Bars must be strictly
oldest-first with unique timestamps; inputs are never modified.

Only closes in [start, as_of] are selected. A close exactly at start can be
provided by the preceding bar. Both endpoints of each return must be selected
and exactly bar_seconds apart. Gaps are not bridged, and partial bars and
future closes are excluded. The caller must keep as_of <= ctx['now'] and must
not supply revisions unavailable at that time; bar timestamps cannot certify
historical publication availability.

For the retained log returns r:
  realized_variance = sum(r*r)
  realized_volatility = sqrt(sum(r*r))
  rms_log_return = sqrt(sum(r*r) / n_returns)

These are unannualized, dimensionless log-return measures, not percentages,
not demeaned sample standard deviations, and not forecasts of remaining-window
risk. Realized volatility grows with the observed horizon. On gaps it measures
only the reported covered intervals, not the whole requested window.

The result also includes n_closes, n_returns, covered_seconds, and complete.
Complete is true only when both requested endpoints are present and all
intervening closes are one cadence apart. No returns means all three estimates
are None and complete is false; a genuinely flat observed path yields zero.
Always inspect coverage and sample count before comparing markets or windows.
"""

import math
from datetime import datetime, timedelta, timezone


def _timestamp(value):
    """Parse a timezone-aware ISO timestamp and normalize it to UTC."""
    if not isinstance(value, str):
        raise ValueError('timestamps must be timezone-aware ISO strings')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid ISO timestamp') from None
    if parsed.utcoffset() is None:
        raise ValueError('timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def window_realized_volatility(bars, start, as_of, bar_seconds=300,
                               timestamp_at='start'):
    """Return sampled realized variation and explicit interval coverage.

    bars contains mappings with t and c; other OHLCV fields are ignored.
    start and as_of are timezone-aware ISO strings with start < as_of.
    bar_seconds is a positive integer. timestamp_at is 'start' or 'end'.
    Selected closes must be positive finite numbers. Invalid configuration,
    timestamps, selected prices, duplicate timestamps, or reversed ordering
    raise ValueError. Missing required mapping keys raise KeyError.
    """
    if (isinstance(bar_seconds, bool)
            or not isinstance(bar_seconds, int) or bar_seconds <= 0):
        raise ValueError('bar_seconds must be a positive integer')
    if timestamp_at not in ('start', 'end'):
        raise ValueError("timestamp_at must be 'start' or 'end'")
    first = _timestamp(start)
    last = _timestamp(as_of)
    if first >= last:
        raise ValueError('start must precede as_of')
    cadence = timedelta(seconds=bar_seconds)
    previous_stamp = None
    closes = []
    for bar in bars:
        stamp = _timestamp(bar['t'])
        if previous_stamp is not None and stamp <= previous_stamp:
            raise ValueError('bar timestamps must be strictly increasing')
        previous_stamp = stamp
        close_time = stamp + cadence if timestamp_at == 'start' else stamp
        if not first <= close_time <= last:
            continue
        price = bar['c']
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError('selected closes must be positive finite numbers')
        try:
            price = float(price)
        except OverflowError:
            raise ValueError('selected close is outside finite float range') from None
        if not math.isfinite(price) or price <= 0:
            raise ValueError('selected closes must be positive finite numbers')
        closes.append((close_time, price))

    squares = []
    for index in range(1, len(closes)):
        before_time, before_price = closes[index - 1]
        after_time, after_price = closes[index]
        if after_time - before_time == cadence:
            # Difference of logs avoids overflowing a price ratio.
            change = math.log(after_price) - math.log(before_price)
            squares.append(change * change)
    count = len(squares)
    variance = math.fsum(squares) if count else None
    complete = bool(
        count and closes[0][0] == first and closes[-1][0] == last
        and count == len(closes) - 1
    )
    return {
        'realized_variance': variance,
        'realized_volatility': math.sqrt(variance) if count else None,
        'rms_log_return': math.sqrt(variance / count) if count else None,
        'n_closes': len(closes),
        'n_returns': count,
        'covered_seconds': count * bar_seconds,
        'complete': complete,
    }
