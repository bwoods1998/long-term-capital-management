"""Sampled realized volatility over an explicit, already elapsed window.

Strategy use::

    from tools.realized_volatility import realized_volatility

    stats = realized_volatility(
        ctx['observed']['bars']['BTC/USD'],
        window_start_iso, ctx['now'], 300, timestamp_at='start')
    # Inspect stats['complete'], stats['coverage'] and stats['n_returns']
    # before interpreting stats['realized_volatility'].

Inputs:
* bars: oldest-first dictionaries with 't' (ISO timestamp) and 'c' (close).
  Timestamps must be unique and strictly increasing. Other fields are ignored.
* window_start and as_of: timezone-aware ISO strings, with start < as_of.
  Use the decision's ctx['now'], not a future settlement time, for as_of.
* bar_seconds: positive integer duration of the supplied bars, in seconds.
* timestamp_at: REQUIRED keyword, 'start' or 'end'. For start-stamped bars,
  a close becomes eligible only at t + bar_seconds. Use the source's documented
  convention; this helper cannot determine it from OHLCV values.

The caller chooses the underlier and window; no market-code parsing or assumed
settlement convention is applied. A close at window_start is an eligible
anchor, even though its bar began before the window. Closes outside the
inclusive [window_start, as_of] bounds are excluded. Only adjacent eligible
closes exactly bar_seconds apart produce a return. Gaps are never bridged,
prices are never interpolated, and partial bars are never used.

For usable returns r = log(c_next) - log(c_previous), realized_variance is
sum(r*r), and realized_volatility is sqrt(realized_variance). These are
non-annualized log-return quantities, without demeaning or extrapolation.
Multiply volatility by 100 for approximate percentage units. This is not a
sample standard deviation, forecast, official settlement volatility, or a
reconstruction of movements hidden inside coarse bars.

The result is a JSON-compatible dictionary with variance and volatility
(None when there are no usable returns), n_closes, n_returns, covered_seconds,
coverage (covered_seconds / requested elapsed seconds), complete, and
last_close_at (UTC ISO string, or None). Complete means contiguous coverage
of this requested elapsed window, not of a future full market window.
Coverage is a data diagnostic, not statistical confidence. A flat observed
return has zero volatility; missing observations do not.

All timestamps are validated, but prices outside the window are not read.
Invalid timestamps, ordering, selected prices or options raise ValueError;
missing required row keys raise KeyError. Naive timestamps, boolean prices
and numeric strings are rejected. Inputs are not mutated. Only supplied
observations are used; the caller/source must ensure they were available
point-in-time and have not been replaced with later historical revisions.
"""

import math
from datetime import datetime, timedelta, timezone


def _time(value):
    if not isinstance(value, str):
        raise ValueError('timestamps must be timezone-aware ISO strings')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def _log_price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('selected closes must be positive finite numbers')
    try:
        price = float(value)
    except (OverflowError, ValueError):
        raise ValueError('selected closes must be positive finite numbers')
    if not math.isfinite(price) or price <= 0:
        raise ValueError('selected closes must be positive finite numbers')
    return math.log(price)


def realized_volatility(bars, window_start, as_of, bar_seconds, *, timestamp_at):
    """Return window-bounded realized variation and explicit coverage diagnostics."""
    if (isinstance(bar_seconds, bool)
            or not isinstance(bar_seconds, int) or bar_seconds <= 0):
        raise ValueError('bar_seconds must be a positive integer')
    if timestamp_at not in ('start', 'end'):
        raise ValueError("timestamp_at must be 'start' or 'end'")
    start = _time(window_start)
    end = _time(as_of)
    if end <= start:
        raise ValueError('as_of must be later than window_start')
    try:
        step = timedelta(seconds=bar_seconds)
    except OverflowError:
        raise ValueError('bar_seconds is outside the supported datetime range')
    offset = step if timestamp_at == 'start' else timedelta(0)
    selected = []
    previous_stamp = None
    for bar in bars:
        stamp = _time(bar['t'])
        if previous_stamp is not None and stamp <= previous_stamp:
            raise ValueError('bar timestamps must be strictly increasing')
        previous_stamp = stamp
        close_at = stamp + offset
        if start <= close_at <= end:
            selected.append((close_at, _log_price(bar['c'])))

    squared_returns = []
    for previous, current in zip(selected, selected[1:]):
        if current[0] - previous[0] == step:
            change = current[1] - previous[1]
            squared_returns.append(change * change)
    count = len(squared_returns)
    variance = math.fsum(squared_returns) if count else None
    covered = count * bar_seconds
    elapsed = (end - start).total_seconds()
    return {
        'realized_variance': variance,
        'realized_volatility': math.sqrt(variance) if count else None,
        'n_closes': len(selected),
        'n_returns': count,
        'covered_seconds': covered,
        'coverage': covered / elapsed,
        'complete': count > 0 and covered == elapsed,
        'last_close_at': selected[-1][0].isoformat() if selected else None,
    }
