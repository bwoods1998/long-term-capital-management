"""Realized volatility over an explicit window of already-visible closed bars.

Usage in a strategy::

    from tools.realized_volatility import window_volatility
    stats = window_volatility(
        ctx['observed']['bars']['BTC/USD'],
        '2026-09-21T12:00:00Z', '2026-09-21T12:15:00Z', 300)
    if stats is not None:
        window_vol = stats['realized_volatility']

Use that example only once the ending observation is closed and visible.
For an unfinished market window, end at the latest available grid point;
that measures the observed prefix, not the full future settlement window.

Inputs are bar mappings with timezone-aware ISO 't' and positive finite
numeric 'c'. start/end are timezone-aware ISO timestamps, inclusive.
step_seconds is a positive integer. End must follow start by a whole number
of steps. N return intervals require N+1 closes, including both boundaries.
Selected observations must be unique and oldest first. Missing boundaries,
missing samples, or off-grid observations return None; gaps are not bridged.
Invalid timestamps, selected closes, ordering, or window arguments raise
ValueError. Missing required mapping keys raise KeyError.

For r_i = log(c_i) - log(c_(i-1)), results are:
  n_returns: number of observed return intervals;
  realized_variance: sum(r_i ** 2), without subtracting the mean;
  realized_volatility: sqrt(realized_variance), in log-return units;
  rms_return: sqrt(realized_variance / n_returns), per supplied step;
  step_seconds: the requested sampling interval.
These are backward-looking, unannualized estimates, not sample standard
 deviation, a forecast, or an official settlement-price measurement.

The caller supplies the market-to-underlier mapping and window boundaries.
Only rows with start <= t <= end contribute. No earlier close is borrowed.
All timestamps are parsed; prices outside the window are ignored. Inputs
are not mutated, fetched, interpolated, or resampled.

IMPORTANT: 't' is used as supplied, not assumed to be a bar's closing time.
Pass only bars already closed and available at ctx['now'], with end no later
than now. If a source labels bars by opening time, translate the desired
close-observation boundaries to that convention before calling. This helper
cannot reconstruct publication delays or detect revised historical inputs.
A complete 15-minute window at five-minute spacing has three returns, not
fifteen; this helper cannot recover missing one-minute price discovery.
"""

from datetime import datetime, timezone
import math


def utc_timestamp(value):
    """Parse a timezone-aware ISO timestamp and normalize it to UTC."""
    if not isinstance(value, str):
        raise ValueError('timestamps must be timezone-aware ISO strings')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid ISO timestamp')
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('timestamps must include a timezone')
    return stamp.astimezone(timezone.utc)


def window_volatility(bars, start, end, step_seconds):
    """Return the module's volatility statistics, or None for incomplete data."""
    if (isinstance(step_seconds, bool)
            or not isinstance(step_seconds, int)
            or step_seconds <= 0):
        raise ValueError('step_seconds must be a positive integer')
    first = utc_timestamp(start)
    last = utc_timestamp(end)
    duration = (last - first).total_seconds()
    if duration <= 0 or duration % step_seconds != 0:
        raise ValueError('window must contain a positive whole number of steps')

    selected = []
    for bar in bars:
        stamp = utc_timestamp(bar['t'])
        if first <= stamp <= last:
            if selected and stamp <= selected[-1][0]:
                raise ValueError('selected timestamps must be unique and increasing')
            close = bar['c']
            if isinstance(close, bool) or not isinstance(close, (int, float)):
                raise ValueError('selected closes must be positive finite numbers')
            try:
                price = float(close)
            except (OverflowError, ValueError):
                raise ValueError('selected close cannot be represented as a float')
            if not math.isfinite(price) or price <= 0:
                raise ValueError('selected closes must be positive finite numbers')
            selected.append((stamp, math.log(price)))

    expected = int(duration // step_seconds) + 1
    if len(selected) != expected:
        return None
    for index, observation in enumerate(selected):
        if (observation[0] - first).total_seconds() != index * step_seconds:
            return None

    returns = [selected[index][1] - selected[index - 1][1]
               for index in range(1, len(selected))]
    variance = math.fsum(value * value for value in returns)
    return {
        'n_returns': len(returns),
        'realized_variance': variance,
        'realized_volatility': math.sqrt(variance),
        'rms_return': math.sqrt(variance / len(returns)),
        'step_seconds': step_seconds,
    }
