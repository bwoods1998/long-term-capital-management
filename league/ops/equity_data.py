"""The `equity_data` job: the equity lane's daily store, Alpaca SIP daily bars through the gateway, raw and adjustment=all.

Owner: ops. Protected (league/ops/ is FORBIDDEN to every role). Registered in league/ops/registry.py the way `direction`
is (at the House's start and daily after the close; in a pause too: it only reads and writes its own directory).

THE JOB (`run`): for the universe (league/equity/config.py `UNIVERSE`, the constitution's `equity_money.universe`
bounding it), page `GET /v1/alpaca/v2/stocks/bars` (the route the gateway already allows; `direction.fetch`'s paging)
with timeframe 1Day, feed sip, `adjustment=raw` and again `adjustment=all`, from 2016-01-04 (`FIRST_DAY`) to the last
CLOSED session (`direction.session_closed`: never a partial day). Then the AUDIT (`audit`), then
`league.equity.store.write_store(<state>/equity-daily, ..., gate=True, source="alpaca-sip-1Day", audit=...)`
atomically. A gateway error or a failed audit writes nothing new: {"status": "failed", "error"} (a failed receipt, a
House warning, a retry inside its grace); the last good store stays.

THE AUDIT (`audit`; each a named check, all must pass):
- calendar: every session of `league.equity.store.nyse_sessions(FIRST_DAY, last)` has a SPY bar and no bar falls on a
  non-session (no gap, no extra day);
- OHLC sane: 0 < low <= min(open, close) <= max(open, close) <= high, for raw and all;
- splits visible: every raw/all ratio jump over `SPLIT_JUMP` lines up with a split the raw close shows (a jump of the
  raw close by the factor), reported per symbol;
- volumes present: every raw bar has volume > 0;
- THE REGULAR SESSION (the design's fact 1; `regular_session_check`): on `REGULAR_DAYS` (20) sessions, the 1Day bar's
  open, high, low, close and volume against the 1Min bars of 09:30-16:00 (13:00 on a half day) aggregated: within
  `REGULAR_TOLERANCE`. The verdict ("regular" | "extended" | "unverified") is recorded in the manifest's audit; if the
  1Day bar includes extended hours the store must be built from 1Min bars (a stop for E1, reported, never patched).

Data never leaves the House's state directory (the vendor's terms; a public repository): nothing here is committed,
printed in full, or sent anywhere but the store.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

FIRST_DAY = "2016-01-04"
STORE_DIR = "equity-daily"
BARS = "/v1/alpaca/v2/stocks/bars"
MAX_PAGES = 400
#: A raw/all ratio move larger than this between two sessions is a corporate action the audit must explain.
SPLIT_JUMP = 0.05
REGULAR_DAYS = 20
REGULAR_TOLERANCE = 1e-6


def fetch(gateway: Any, symbols: Sequence[str], start: str, end: str, *, adjustment: str,
          timeframe: str = "1Day") -> dict[str, list[dict[str, Any]]]:
    """{symbol: [bar rows {t, o, h, l, c, v} in time order]} of every page; ValueError on a malformed answer or a cursor
    that does not end within `MAX_PAGES`."""
    raise NotImplementedError("ops: league/ops/equity_data.py fetch")


def regular_session_check(gateway: Any, symbol: str, days: Sequence[dt.date]) -> dict[str, Any]:
    """The design's fact 1 on `days`: {verdict "regular" | "extended" | "unverified", days, mismatches: [...]}."""
    raise NotImplementedError("ops: league/ops/equity_data.py regular_session_check")


def audit(calendar: Sequence[tuple[dt.date, bool]], raw: Mapping[str, Sequence[Mapping[str, Any]]],
          adj: Mapping[str, Sequence[Mapping[str, Any]]], *, regular: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """{passed, checks: {calendar, ohlc, splits, volume, regular}: each {passed, problems: [...] (at most 20)}}."""
    raise NotImplementedError("ops: league/ops/equity_data.py audit")


def run(ctx: Any) -> dict[str, Any]:
    """The job (the module docstring): {"ok": True, "symbols", "sessions", "fetched_through", "audit"} or
    {"status": "failed", "ok": False, "error"}."""
    raise NotImplementedError("ops: league/ops/equity_data.py run")


__all__ = ["FIRST_DAY", "STORE_DIR", "BARS", "MAX_PAGES", "SPLIT_JUMP", "REGULAR_DAYS", "REGULAR_TOLERANCE", "fetch",
           "regular_session_check", "audit", "run"]
