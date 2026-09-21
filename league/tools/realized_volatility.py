'''Realised volatility over an explicit window of supplied closed spot bars.

Strategy usage:
    from tools.realized_volatility import window_realized_volatility
    result = window_realized_volatility(
        ctx['observed']['bars'].get('BTC/USD', []),
        window_start, window_end, ctx['now'], 300,
        timestamp_at='open',
    )

Use timestamp_at='open' ONLY when bar t is the opening timestamp; use
'close' when t denotes the close. Confirm the producer's convention.
For opening-stamped bars, a close becomes eligible at t + bar_seconds.
All timestamps must be timezone-aware ISO strings. Inputs are oldest first.
The caller supplies the true observation-window bounds; do not assume that
market close_time identifies the settlement observation window.

Eligible closes satisfy window_start <= close_time <= min(window_end, as_of).
A close exactly at window_start is the baseline for the first return, even
if that baseline comes from a bar opening before the window. No preceding
close outside the window is used. Prices outside the eligible interval are
ignored. Selected closes must be finite positive JSON numbers.

For contiguous eligible prices p[0], ..., p[n], variance is
    sum((log(p[i]) - log(p[i-1])) ** 2 for i in 1..n)
and volatility is sqrt(variance). This is unannualised realised quadratic
variation, NOT demeaned sample variance, a remaining-window forecast, or a
settlement probability. Volatility is in log-return units, not percent.

The JSON-compatible result contains status ('ok', 'insufficient', 'gapped'),
variance, volatility, n_closes, bar_seconds, first_close_at, last_close_at,
span_seconds, and complete. Fewer than two closes gives None estimates.
Any selected adjacent closes not exactly bar_seconds apart gives 'gapped'
and None estimates; there is no interpolation or hidden resampling.
'complete' requires contiguous observations at both requested boundaries.
An 'ok' but incomplete result describes only its reported sample span.
A single return is computable but is not a reliable volatility forecast.

Bar timestamps must be strictly increasing throughout the supplied input;
duplicates and out-of-order rows are rejected rather than silently repaired.
Input bars must already be point-in-time, revision-safe observations. This
helper cannot validate source availability or undo revised historical bars.
It cannot create 1Min data from 5Min bars, add settlement-source mappings,
align missing Kalshi quotes, or change the strategy/replay wake cadence.
No files, network, global state changes, or input mutation are used.
'''

import math
from datetime import datetime, timedelta, timezone


def _utc(value):
    if not isinstance(value, str):
        raise ValueError('timestamps must be timezone-aware ISO strings')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def window_realized_volatility(bars, window_start, window_end, as_of,
                              bar_seconds, *, timestamp_at):
    '''Return an as-of-filtered window estimate; see the module contract.'''
    if (isinstance(bar_seconds, bool)
            or not isinstance(bar_seconds, int) or bar_seconds <= 0):
        raise ValueError('bar_seconds must be a positive integer')
    if timestamp_at not in ('open', 'close'):
        raise ValueError("timestamp_at must be 'open' or 'close'")
    start = _utc(window_start)
    end = _utc(window_end)
    now = _utc(as_of)
    if end <= start:
        raise ValueError('window_end must be after window_start')
    step = timedelta(seconds=bar_seconds)
    offset = step if timestamp_at == 'open' else timedelta(0)
    cutoff = min(end, now)
    points = []
    previous_time = None
    for bar in bars:
        close_time = _utc(bar['t']) + offset
        if previous_time is not None and close_time <= previous_time:
            raise ValueError('bar timestamps must be strictly increasing')
        previous_time = close_time
        if start <= close_time <= cutoff:
            raw_price = bar['c']
            if (isinstance(raw_price, bool)
                    or not isinstance(raw_price, (int, float))):
                raise ValueError('selected closes must be finite positive numbers')
            try:
                price = float(raw_price)
            except OverflowError:
                raise ValueError('selected close is not a finite float')
            if not math.isfinite(price) or price <= 0:
                raise ValueError('selected closes must be finite positive numbers')
            points.append((close_time, price))

    count = len(points)
    status = 'insufficient'
    variance = None
    volatility = None
    complete = False
    if count >= 2:
        if any(points[i][0] - points[i - 1][0] != step
               for i in range(1, count)):
            status = 'gapped'
        else:
            status = 'ok'
            variance = math.fsum(
                (math.log(points[i][1]) - math.log(points[i - 1][1])) ** 2
                for i in range(1, count)
            )
            volatility = math.sqrt(variance)
            complete = points[0][0] == start and points[-1][0] == end

    return {
        'status': status,
        'variance': variance,
        'volatility': volatility,
        'n_closes': count,
        'bar_seconds': bar_seconds,
        'first_close_at': points[0][0].isoformat() if points else None,
        'last_close_at': points[-1][0].isoformat() if points else None,
        'span_seconds': (points[-1][0] - points[0][0]).total_seconds()
                        if points else 0.0,
        'complete': complete,
    }
