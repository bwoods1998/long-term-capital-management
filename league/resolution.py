"""The horizon rule's answer: when a Kalshi market is expected to pay, and what that is judged by.

A money judge, in `league/ci.py`'s `FORBIDDEN`: the book refuses a Kalshi entry expected to pay past
the agent's horizon (`Limits.max_hours_to_resolve`), and this module is the whole of what "expected
to pay" means -- for the book's check, the House's check before it, the live view a strategy reads
and a replay tape's steps (`league/tapes.py` reads it from here). An updater release cannot change
it; only the owner's deploy can (review of #249, Sept 24, 2026).

What it reads that the House writes -- the settled markets on record, `settle_lags.json` beside the
House's state -- is runtime data, and it is read here as data it cannot trust: an entry that is not
three finite times with the settlement at or after the close and the deadline at least
`DEADLINE_AFTER_CLOSE_SECONDS` after it is ignored, each measured lag is clamped to [0, its own
deadline], a series needs `SETTLE_LAG_MIN_MARKETS` good entries to be measured at all, and the lag
applied to a market is clamped again to [0, that market's deadline]. So no file, however written,
moves a market's expected payment before its close or after its deadline, and a series with fewer
than 20 settlements on record is judged by the deadline, as before.

Standard library only; it imports nothing from the rest of the league.
"""

from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, NamedTuple

#: What a market's expected payment is judged by (`resolution`): SCHEDULED, the venue's expected
#: expiration; CLOSE, the close where the venue gives none; SETTLE_LAG, the close plus its series'
#: measured settle lag, where the expected expiration is a deadline; DEADLINE, that deadline itself
#: where the lag cannot be measured (the rule before the review of #249).
SCHEDULED, CLOSE, SETTLE_LAG, DEADLINE = "scheduled", "close", "settle_lag", "deadline"
#: An "expected" expiration this long after the close is a deadline, not a schedule: the latest the
#: market may expire when its data comes late. Measured on the local history cache (settled markets
#: of Sept 5-17, 2026): 479 of 1,683 series list it six days or more after the close (the diesel
#: prints 169.5 hours, the AI-share weeklies 168), while their markets paid within hours.
DEADLINE_AFTER_CLOSE_SECONDS = 48 * 3600
#: The settle lag (`settle_lag`): the 95th percentile of (settlement - close) over a series' last
#: `SETTLE_LAG_MARKETS` deadline-type settled markets, at least `SETTLE_LAG_MIN_MARKETS` of them.
SETTLE_LAG_MARKETS = 40
SETTLE_LAG_MIN_MARKETS = 20
SETTLE_LAG_QUANTILE = 0.95
#: Settled markets kept per series (the newest), enough for any replay window's days.
SETTLE_LAG_KEEP = 400
DAY = 86400


class Resolution(NamedTuple):
    """`resolution`'s answer: when the market is expected to pay (epoch seconds), what that is judged
    by, and for SETTLE_LAG the lag (hours) and how many settled markets measured it. `deadline` is the
    venue's expected expiration where it is a deadline (SETTLE_LAG, DEADLINE)."""
    due: float
    basis: str
    lag_hours: "float | None" = None
    markets: "int | None" = None
    deadline: "float | None" = None


def _time(value: Any) -> "float | None":
    """An ISO-8601 stamp (a bare one is UTC) or epoch seconds, as finite epoch seconds; else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    head, dot, rest = raw.partition(".")
    if dot:  # at most six fractional digits for `fromisoformat` (Alpaca-style nanoseconds)
        digits = len(rest) - len(rest.lstrip("0123456789"))
        raw = head + "." + rest[:min(digits, 6)] + rest[digits:]
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    stamp = moment.timestamp()
    return stamp if math.isfinite(stamp) else None


def series_of(row: "dict[str, Any]") -> str:
    """The Kalshi series of a market row: its ticker's first segment."""
    return str(row.get("ticker") or row.get("market") or "").upper().split("-", 1)[0]


def expected_of(row: "dict[str, Any]") -> "float | None":
    """The venue's expected expiration of a market row (epoch seconds), or None where it gives none."""
    value = _time(row.get("expected_expiration_time")) if row.get("expected_expiration_time") else None
    return value if value is not None and value > 0 else None


def is_deadline(expected: "float | None", close_ts: float) -> bool:
    """Whether an expected expiration is a DEADLINE (`DEADLINE_AFTER_CLOSE_SECONDS` or more after the
    close) rather than a schedule."""
    return expected is not None and expected - close_ts >= DEADLINE_AFTER_CLOSE_SECONDS


def _observation(value: Any) -> "tuple[float, float, float] | None":
    """(close, settled, deadline) from one kept entry, or None where it cannot be trusted: not three
    finite positive numbers, a settlement before its close, or a deadline that is not one."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        close_ts, settled, deadline = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and v > 0 for v in (close_ts, settled, deadline)):
        return None
    if settled < close_ts or not is_deadline(deadline, close_ts):
        return None
    return close_ts, settled, deadline


def settle_lag(observations: "Iterable[Any]", at: float) -> "tuple[float, int] | None":
    """(the lag in seconds, how many settled markets measured it), or None: the 95th percentile of
    (settlement - close), each clamped to [0, its own deadline - close], over the last
    `SETTLE_LAG_MARKETS` good observations (`_observation`) that settled before `at`'s UTC midnight,
    with at least `SETTLE_LAG_MIN_MARKETS` of them. A replay at `t` reads only settlements known
    before `t`, and one value holds for a whole day."""
    try:
        day = math.floor(float(at) / DAY) * DAY
    except (TypeError, ValueError, OverflowError):
        return None
    good = [found for found in (_observation(v) for v in observations) if found is not None and found[1] < day]
    good.sort(key=lambda o: o[1])
    good = good[-SETTLE_LAG_MARKETS:]
    if len(good) < SETTLE_LAG_MIN_MARKETS:
        return None
    lags = sorted(min(max(0.0, settled - close_ts), deadline - close_ts) for close_ts, settled, deadline in good)
    return lags[math.ceil(SETTLE_LAG_QUANTILE * len(lags)) - 1], len(lags)


class SettleLags:
    """When a Kalshi series' deadline-type markets paid after their close, on the House's own record.

    Only deadline-type markets are kept, from the settled rows the House already reads: every Kalshi
    replay tape passes its settled markets through `observe` (`league.tapes.KalshiData`, which reads
    them from `ltcm.history` and its disk cache as it always has), so measuring asks the venue
    nothing. Kept in `path` (`settle_lags.json` beside the House's state) so a restart keeps them; the
    file is data, and every entry of it is judged again when read (`_observation`, `settle_lag`).

    `lag(series, at)` is `settle_lag` over the series' entries at `at`: one value a series a day, kept
    once measured (recomputed at most daily), the same for the live book, the House and a replay
    tape's steps of that day."""

    VERSION = 1

    def __init__(self, path: Any = None):
        self.path = Path(path) if path else None
        self._rows: dict[str, dict[str, tuple[float, float, float]]] = {}
        self._memo: dict[tuple[str, int], tuple[float, int]] = {}
        self._lock = threading.Lock()
        self._dirty = False
        if self.path is not None and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            series_map = data.get("series") if isinstance(data, dict) else None
            for series, markets in (series_map.items() if isinstance(series_map, dict) else ()):
                if not isinstance(series, str) or not isinstance(markets, dict):
                    continue
                kept = {str(t): found for t, v in markets.items() if (found := _observation(v)) is not None}
                if kept:
                    self._rows[series.upper()] = kept

    def observe(self, rows: "Iterable[dict[str, Any]]") -> int:
        """Keep the deadline-type markets among these settled rows. Returns how many were new."""
        added = 0
        with self._lock:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                close_ts, settled, expected = _time(row.get("close_time")), _time(row.get("settlement_ts")), expected_of(row)
                found = _observation((close_ts, settled, expected)) if None not in (close_ts, settled, expected) else None
                ticker, series = str(row.get("ticker") or "").upper(), series_of(row)
                if found is None or not ticker or not series:
                    continue
                markets = self._rows.setdefault(series, {})
                if ticker not in markets:
                    added += 1
                markets[ticker] = found
                if len(markets) > SETTLE_LAG_KEEP:
                    for old, _ in sorted(markets.items(), key=lambda kv: kv[1][1])[: len(markets) - SETTLE_LAG_KEEP]:
                        markets.pop(old, None)
            self._dirty = self._dirty or added > 0
        return added

    def observations(self, series: str) -> "list[tuple[float, float, float]]":
        with self._lock:
            return list((self._rows.get(str(series).upper()) or {}).values())

    def lag(self, series: str, at: float) -> "tuple[float, int] | None":
        """`settle_lag` of `series` at `at`, kept for the day once measured."""
        try:
            day = int(math.floor(float(at) / DAY) * DAY)
        except (TypeError, ValueError, OverflowError):
            return None
        key = (str(series).upper(), day)
        with self._lock:
            if key in self._memo:
                return self._memo[key]
            found = settle_lag((self._rows.get(key[0]) or {}).values(), at)
            if found is not None:  # not kept while unmeasured: the day's value appears once enough are on record
                self._memo[key] = found
            return found

    def save(self) -> None:
        """Write what is kept, if anything new came in (atomically; two tapes may save at once)."""
        if self.path is None:
            return
        with self._lock:
            if not self._dirty:
                return
            data = {"version": self.VERSION, "series": {s: {t: list(v) for t, v in m.items()} for s, m in self._rows.items()}}
            self._dirty = False
        tmp = self.path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            with self._lock:
                self._dirty = True  # asked again after the next tape


def resolution(row: "dict[str, Any]", close_ts: float, *, lags: "SettleLags | None" = None, at: "float | None" = None) -> Resolution:
    """When a market is expected to pay, and what that is judged by -- the horizon rule's one answer.

    - SCHEDULED: the venue's expected expiration, which a listing shows from the day it opens and
      never changes. (Measured Sept 19, 2026: a game's `close_time` is two days after kickoff and it
      really closes when a winner is declared, near its expected expiration; a weather market stops
      trading at `close_time` and is paid at its expiration, about 14 hours later.)
    - SETTLE_LAG: where that "expected" expiration is a deadline (`is_deadline`), the market is
      judged by its close plus its series' measured settle lag (`SettleLags.lag` at `at`), clamped to
      [0, the deadline]: never before the close, never after the deadline. Review of #249: the diesel
      prints list theirs 169.5 hours after the close (the horizon rule refused 71 KXDIESELD entries on
      Sept 20-22 as "expected to resolve in 171-185 hours") while the last 40 cached diesel dailies
      paid within 5.9 hours of the close (p95).
    - DEADLINE: that deadline, where the lag cannot be measured: no `SettleLags`, or fewer than
      `SETTLE_LAG_MIN_MARKETS` good settlements of the series on record -- the rule before.
    - CLOSE: the close, where the venue lists no expected expiration (none seen).

    Never the deprecated `expiration_time` the parser falls back to (the latest expiration)."""
    expected = expected_of(row)
    if expected is None:
        return Resolution(close_ts, CLOSE)
    if not is_deadline(expected, close_ts):
        return Resolution(expected, SCHEDULED)
    measured = lags.lag(series_of(row), at) if isinstance(lags, SettleLags) and at is not None else None
    try:
        lag, markets = (float(measured[0]), int(measured[1])) if measured is not None else (float("nan"), 0)
    except (TypeError, ValueError, IndexError):
        lag, markets = float("nan"), 0
    if not math.isfinite(lag) or markets < SETTLE_LAG_MIN_MARKETS:
        return Resolution(expected, DEADLINE, deadline=expected)
    lag = min(max(0.0, lag), expected - close_ts)
    return Resolution(close_ts + lag, SETTLE_LAG, round(lag / 3600.0, 2), markets, expected)


def resolve_time(row: "dict[str, Any]", close_ts: float, *, lags: "SettleLags | None" = None, at: "float | None" = None) -> float:
    """When a market is expected to pay (epoch seconds): `resolution`'s time."""
    return resolution(row, close_ts, lags=lags, at=at).due
