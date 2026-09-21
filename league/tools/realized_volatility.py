"""Causal close-to-close realized volatility for an explicit observation window.

Import in a strategy::

    from tools.realized_volatility import window_realized_volatility

    stats = window_realized_volatility(
        ctx['observed']['bars']['BTC/USD'],
        window_start, window_end, ctx['now'],
        bar_seconds=300, timestamp='start',
    )

The caller must establish the market's underlying and actual observation-window
boundaries; this module does not infer them from a ticker or close_time. All
three time arguments and bar 't' fields are timezone-aware ISO-8601 strings.
Use bar_seconds=60 only for genuine one-minute bars. Set timestamp='start' when
bar 't' labels its opening time, or 'end' when it labels its closing time. Bars
are dictionaries with 't' and positive finite numeric 'c', oldest first with
strictly increasing timestamps. Input is never mutated.

For window start s, duration h, and cutoff min(as_of, window_end), sample closes
on the grid s, s+h, ..., through the cutoff. A close at s is REQUIRED as the
baseline (usually supplied by the preceding bar); no bar-open substitution is
made. The window duration must be a positive multiple of h. Selected closes
must lie exactly on this grid. Older/future bar prices are ignored, although
all input timestamps and their ordering are validated. A bar is usable only
once it has closed; the caller must also supply it no earlier than its actual
availability. The helper cannot infer an unrecorded publication delay.

For N available adjacent returns, r_i = log(c_i) - log(c_(i-1)), the estimator is
RV = sum(r_i**2), and realized volatility is sqrt(RV). It is an unannualized
log-return magnitude, not a percentage, sample standard deviation, forecast,
or official settlement statistic. It is not demeaned or scaled to a full
window. Compare like sampling frequencies AND like elapsed durations.

The result contains realized_variance, realized_volatility, return_count,
expected_return_count, sample_count, bar_seconds, complete, and window_complete.
'complete' means every elapsed grid return from the window start is present
and at least one return exists. Before window end this can describe a complete
PREFIX only. 'window_complete' additionally requires as_of >= window_end.
Missing baseline/interior samples or zero elapsed returns produce None for
both estimates. return_count counts only adjacent available grid pairs; gaps
are never bridged or filled. Flat, fully covered prices correctly produce 0.

Invalid time arguments, selected prices, ordering, grid alignment, or sampling
options raise ValueError. This helper needs no files, network, or mutable state.
"""

import math
from datetime import datetime, timedelta, timezone


def _utc(value):
    if not isinstance(value, str):
        raise ValueError('timestamps must be timezone-aware ISO strings')
    text = value[:-1] + '+00:00' if value.endswith('Z') else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError('invalid ISO timestamp') from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def _price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('selected closes must be positive finite numbers')
    try:
        price = float(value)
    except (OverflowError, ValueError):
        raise ValueError('selected closes must be positive finite numbers') from None
    if not math.isfinite(price) or price <= 0:
        raise ValueError('selected closes must be positive finite numbers')
    return price


def window_realized_volatility(bars, window_start, window_end, as_of,
                              bar_seconds=60, timestamp='start'):
    """Return unannualized squared-log-return statistics; see module contract."""
    if (isinstance(bar_seconds, bool)
            or not isinstance(bar_seconds, int) or bar_seconds <= 0):
        raise ValueError('bar_seconds must be a positive integer')
    if timestamp not in ('start', 'end'):
        raise ValueError("timestamp must be 'start' or 'end'")

    start = _utc(window_start)
    end = _utc(window_end)
    now = _utc(as_of)
    duration = (end - start).total_seconds()
    if duration <= 0 or duration % bar_seconds != 0:
        raise ValueError('window duration must be a positive multiple of bar_seconds')
    cutoff = min(now, end)
    elapsed = max(0.0, (cutoff - start).total_seconds())
    expected = int(elapsed // bar_seconds)
    offset = timedelta(seconds=bar_seconds if timestamp == 'start' else 0)

    points = {}
    previous = None
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError('each bar must be a dictionary')
        stamped = _utc(bar.get('t'))
        if previous is not None and stamped <= previous:
            raise ValueError('bar timestamps must be strictly increasing')
        previous = stamped
        closed = stamped + offset
        if closed < start or closed > cutoff:
            continue
        seconds = (closed - start).total_seconds()
        if seconds % bar_seconds != 0:
            raise ValueError('selected closes must align with the window grid')
        points[int(seconds // bar_seconds)] = _price(bar.get('c'))

    returns = []
    for index in sorted(points):
        if index > 0 and index - 1 in points:
            # Subtract logs instead of forming a potentially overflowing ratio.
            returns.append(math.log(points[index]) - math.log(points[index - 1]))
    complete = expected > 0 and len(returns) == expected
    variance = math.fsum(r * r for r in returns) if complete else None
    return {
        'realized_variance': variance,
        'realized_volatility': math.sqrt(variance) if complete else None,
        'return_count': len(returns),
        'expected_return_count': expected,
        'sample_count': len(points),
        'bar_seconds': bar_seconds,
        'complete': complete,
        'window_complete': complete and now >= end,
    }
