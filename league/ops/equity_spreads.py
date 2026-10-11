"""The `equity_spreads` job: each panel name's half-spread at the instants the book trades (D20).

Owner: package B of release E4. Protected (league/ops/). STEP 0 STUB: the constants are the contract; every function
raises NotImplementedError until B lands. The registry row is package A's patch (E4-SPEC 13).

A sample is the median over the quotes of one `WINDOW_S`-second window of (ask - bid) / (ask + bid), quotes with bid >
0 and ask > bid, from `GET /v1/alpaca/v2/stocks/quotes` (one symbol, one window, `sort=asc`, `feed=sip`, `asof`
inside the name's spell). Samples come from the six `league.xs.config.TRAIN_YEARS` only (a cost table must not read a
sealed year), `SESSIONS_YEAR` sessions a year, at `TIMES_ET`: 09:32:00, when the book sends its entries (at 09:30:30
many NYSE names have not had their opening print), and 15:55:00. A sample above `league.xs.config.HS_MAX_BP` is
DROPPED and counted (the book sends no entry on a quote wider than 2% of the mid). Resumable from spreads.json, at
most `CALLS_RUN` calls a run (about 49,000 in all); then monthly, new assets only. Package A's next run turns the
table into panel/hs.npy.

The receipt carries counts and shares, never a quote, a price or a ticker.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

QUOTES = "/v1/alpaca/v2/stocks/quotes"
TIMES_ET = ("09:32:00", "15:55:00")
#: The first week's report-only comparison instant (fact 3: how much the instant matters).
EARLY_ET = "09:30:30"
EARLY_NAMES = 20
WINDOW_S = 2
SESSIONS_YEAR = 8
LIMIT = 50
CALLS_RUN = 6000
MIN_SAMPLES = 8
DROPPED_WARNING = 0.10
VERSION = "xs-spreads-v1"
FILE = "spreads.json"
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 3000

_STUB = "league.ops.equity_spreads is a Step 0 stub: package B builds it (league/xs/E4_INTERFACES.md)"


def sample_days(calendar: Sequence[tuple[dt.date, bool]]) -> dict[int, list[dt.date]]:
    """{year: [day]} for the six Train years: session index round((j + 0.5) x n / 8), j = 0..7; a half day moves to
    the next full session."""
    raise NotImplementedError(_STUB)


def sample(gateway: Any, symbol: str, day: dt.date, time_et: str, *, asof: str | None) -> float | None:
    """One sample (a half-spread fraction) of `symbol` at `time_et` of `day`, or None when the window holds no valid
    quote."""
    raise NotImplementedError(_STUB)


def summarize(samples: Mapping[Any, Any]) -> dict[str, Any]:
    """spreads.json's `names`, `default` and `dropped` from the samples (D20): per name and fill point the 75th
    percentile of its kept samples and their count; the universe's 75th percentile; the dropped share by listing
    exchange and fill point (a share above `DROPPED_WARNING` at either is a warning)."""
    raise NotImplementedError(_STUB)


def run(ctx: Any) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`."""
    raise NotImplementedError(_STUB)


__all__ = ["QUOTES", "TIMES_ET", "EARLY_ET", "EARLY_NAMES", "WINDOW_S", "SESSIONS_YEAR", "LIMIT", "CALLS_RUN",
           "MIN_SAMPLES", "DROPPED_WARNING", "VERSION", "FILE", "WALL_S", "sample_days", "sample", "summarize", "run"]
