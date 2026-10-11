"""The `equity_panel` job: the panel's bars, its store, the coverage audit and the nightly I6 on real data.

Owner: package A of release E4. Protected (league/ops/). STEP 0 STUB: the constants are the contract; every function
raises NotImplementedError until A lands. It stands on package C's C0 (`league.xs.store.write_panel`,
`league.xs.config`); the registry row is A's patch (E4-SPEC 13: after `equity_universe`).

PER RUN: `league.xs.config.quiet(now, WALL_S)` first; the universe (league/ops/equity_universe.py's files); REF and
member bars for `league.xs.config.SPANS`, through `GET /v1/alpaca/v2/stocks/bars` with the venue's `asof` (`fetch_asof`:
open spells together at today's, each ended spell at a day inside it, so a reused ticker resolves to the spell's own
company); 2020 IS NEVER FETCHED (ValueError for a span touching it). THE ADJ VINTAGE: `adj` of one asset is always ONE
fetch's series; the daily run fetches the last 7 sessions of every active asset, appends an asset whose adj/raw close
ratios on the overlap equal the store's within the vendor's cents (`league.xs.config.rounding_bound`), and refetches
whole any other (a dividend or split restated its history); a full refetch of every asset runs when `full_at` is
older than 6.5 days, and falls back to the incremental when a call still fails after its 3 tries.

D19, COVERAGE AND WHAT MAY MASK A MEMBER. A spell's series is ACCEPTED when valid closes cover at least
`ACCEPT_SHARE` of its sessions in the store and its first valid bar is within `ACCEPT_FIRST` sessions of its first
session there; else masked "no_bars" ("reused" when the series' median dollar volume is under `REUSED_USD`). The only
other masks are the venue's "not_fractionable" and "insane" (OHLC sanity failing on more than 1% of the asset's bars).
A BIG MOVE NEVER MASKS: a raw close move past E1's `RAW_JUMP` with no ratio jump is COUNTED and given a SECOND READ
(the 1Min bars of that session and the one before); only when the minute bars contradict the daily bar by more than
2% is that one bar treated as missing. A zero-volume bar is a missing bar for that day, never a mask. coverage[y] =
member-days of year y with a valid bar of an unmasked asset / member-days of y; verdict "ok" | "low_coverage" |
"insufficient" (league/xs/store.py). The run FAILS (nothing written) only when a REF fails E1's audit or over 5% of
current members are masked.

THE NIGHTLY I6 (`i6_check`), both sides of each part built under ONE run key and ONE aid set: (1) the reference ctx of
`fetched_through` from the store's arrays against the same from the KEPT 16:20 fetch (`league.xs.book.kept`) when a
panel instance decided that day, else from a fresh 253-session fetch; (2) each live decision of that day
(`eq_rebalances`, read-only) rebuilt from the store against the kept file, by E1's `_bars_verdict`. A False is a
critical alarm. The job emits a boolean a part and two shas, nothing else.

Data never leaves the House's state directory. The receipt carries counts and verdicts, never a price or a ticker.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Mapping, Sequence

BARS = "/v1/alpaca/v2/stocks/bars"
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 3300
TRIES = 3
BACKOFF_S = (5, 20)
INCREMENTAL_SESSIONS = 7
FULL_EVERY_DAYS = 6.5
ACCEPT_SHARE = 0.95
ACCEPT_FIRST = 5
REUSED_USD = 5_000_000.0
INSANE_SHARE = 0.01
SECOND_READ_GAP = 0.02
MASKED_MEMBERS_MAX = 0.05
REVISIONS_ALARM = 20
#: The reference NEEDS of the nightly I6's first part.
I6_NEEDS = {"panel": "sp500", "history": 252, "max_names": 12, "rebalance": "weekly", "weekday": 0,
            "max_hold_sessions": 60}

_STUB = "league.ops.equity_panel is a Step 0 stub: package A builds it (league/xs/E4_INTERFACES.md)"


def fetch_asof(gateway: Any, symbols: Sequence[str], start: str, end: str, *, adjustment: str,
               asof: str | None, tries: int = TRIES) -> dict[str, list[dict[str, Any]]]:
    """{symbol: [1Day bar rows in time order]} (E1's `equity_data.fetch` paging with the venue's `asof`; None: the
    venue's own default, today). Each call is tried up to `tries` times, backing off `BACKOFF_S`. ValueError for a
    span touching 2020: "2020 is never fetched"."""
    raise NotImplementedError(_STUB)


def plan(assets: Mapping[str, Any], days: Sequence[dt.date]) -> list[tuple[str | None, list[str], str, str]]:
    """[(asof, symbols, start, end)]: open spells together at today's `asof`, each ended spell at its own; no span
    touches 2020."""
    raise NotImplementedError(_STUB)


def incremental(root: str | Path, gateway: Any, last: dt.date) -> dict[str, Any]:
    """The daily run's arrays (the module docstring's vintage rule): {days, early, aids, raw, adj, vintage, revisions,
    calls}."""
    raise NotImplementedError(_STUB)


def full(root: str | Path, gateway: Any, last: dt.date) -> dict[str, Any]:
    """The weekly whole refetch (about 700 calls, one a spell), same shape as `incremental`. Raises on a call that
    still fails after its tries: `run` then falls back to `incremental` and `full_at` does not move."""
    raise NotImplementedError(_STUB)


def acceptance(series: Mapping[str, Any], spell: Sequence[Any]) -> str | None:
    """D19: None when the spell's series is accepted, else its mask ("no_bars" | "reused" | "insane")."""
    raise NotImplementedError(_STUB)


def second_read(gateway: Any, symbol: str, day: dt.date, *, asof: str | None) -> bool | None:
    """D19's second read of a big move: True when the 1Min bars agree with the daily bar, False when they contradict
    it by more than `SECOND_READ_GAP`, None when they cannot be read (the bar stands)."""
    raise NotImplementedError(_STUB)


def coverage(member: Any, raw: Any, days: Sequence[dt.date], *, masked: Sequence[bool] | None = None,
             floor: float = 0.97) -> dict[str, Any]:
    """D19: {"coverage": {year: {"member_days", "with_bar", "share"}}, "train_years_ok": [...], "verdict"}."""
    raise NotImplementedError(_STUB)


def hs_table(root: str | Path, aids: Sequence[int]) -> Any:
    """D20: float64 (len(aids), 2), the half-spread fraction at the open and at the close, from spreads.json: max(the
    floor, the 75th percentile of the name's samples); fewer than 8 samples: the universe's 75th percentile; no file:
    `league.xs.config.HS_FALLBACK_BP`. Never below `league.xs.config.HS_FLOOR_BP`."""
    raise NotImplementedError(_STUB)


def i6_check(root: str | Path, gateway: Any, day: dt.date, *, live: str | Path | None = None) -> dict[str, Any]:
    """The nightly I6 of `day` (the module docstring): {"day", "store_sha", "fetch_sha", "equal", "source": "kept" |
    "fetch", "live": {instance: bool}}. `live`: live.sqlite's path (opened read-only), None: no live decision."""
    raise NotImplementedError(_STUB)


def run(ctx: Any) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`."""
    raise NotImplementedError(_STUB)


__all__ = ["BARS", "WALL_S", "TRIES", "BACKOFF_S", "INCREMENTAL_SESSIONS", "FULL_EVERY_DAYS", "ACCEPT_SHARE",
           "ACCEPT_FIRST", "REUSED_USD", "INSANE_SHARE", "SECOND_READ_GAP", "MASKED_MEMBERS_MAX", "REVISIONS_ALARM",
           "I6_NEEDS", "fetch_asof", "plan", "incremental", "full", "acceptance", "second_read", "coverage",
           "hs_table", "i6_check", "run"]
