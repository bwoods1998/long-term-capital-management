"""The `equity_universe` job: the point-in-time S&P 500 membership from a free source, and its audit.

Owner: package A of release E4. Protected (league/ops/ is FORBIDDEN to every role). STEP 0 STUB: the constants are the
contract; every function raises NotImplementedError until A lands. The registry row is A's patch (E4-SPEC 13).

THE HOUSE HAS NO OPEN-WEB EGRESS: public pages come through the gateway's reader, `POST /v1/web/fetch {"url", "agent"}`
(text types only, 2 MB of body, 200,000 characters of text), and Alpaca's assets through `GET /v1/alpaca/v2/assets/
<SYM>`.

THE SOURCE: github.com/fja05680/sp500 (MIT), file sp500_ticker_start_end.csv (ticker,start_date,end_date), at a PINNED
commit (`PIN`: a commit sha is not market data). THE PRESENT: changes after the file's `known_through` come from the
English Wikipedia article's "Selected changes" table (MediaWiki `action=parse`), read newest first; a row applies when
its removed ticker is a member and its added one is not, once two runs at least 20 hours apart have both read it. The
table may arrive CUT: only the complete rows above the cut are parsed, and it is VERIFIED only when they reach back to
`known_through`; else `wiki.verdict` "unverified" and nothing is applied. HOW EACH SPELL ENDED (`exits`): "deal" when
the change row's reason matches `league.xs.config.VANISH_DEAL`, "other" when it does not, "unknown" when no complete
row was read: a membership fact, never a price; counted beside results, it sets no price (the pre-registered exit law).

THE AUDIT (all must pass, else nothing is written and the last good universe stays): `source` (the pinned file's
sha256 equals the one recorded at its first fetch), `append_only`, `count` (480 to 520 members on every store
session), `overlap` (no ticker in two overlapping spells), `assets` (at most 10 current members without an active,
tradable Alpaca asset), `wiki_agreement` (reported, never failing). The pin advances weekly (`latest_commit`), only
when `append_only` and the audit pass. `SALT` is written once (`league.xs.store.SALT_FILE`).

What it writes: `<state>/equity-daily/universe/` (league/xs/store.py's layout). The receipt carries counts and
verdicts, never a ticker list, a date of a membership change, or a price. NOTHING HERE IS EVER COMMITTED: the
point-in-time table lives on the House only (the one committed list is the dateless tradable union, `tradable`).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

#: The source's pinned commit (40 hex). EMPTY UNTIL PACKAGE A PINS IT: the job refuses to run without a pin.
PIN = ""
REPO = "fja05680/sp500"
FILE = "sp500_ticker_start_end.csv"
RAW = "https://raw.githubusercontent.com/fja05680/sp500/{commit}/sp500_ticker_start_end.csv"
ATOM = "https://github.com/fja05680/sp500/commits/master.atom"
WEB = "/v1/web/fetch"
ASSETS = "/v1/alpaca/v2/assets/"
AGENT = "equity_universe"
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 900
MEMBERS_MIN, MEMBERS_MAX = 480, 520
ASSETS_MISSING_MAX = 10
#: D2r: two spells within this many calendar days are one asset when their bars agree on at least `RENAME_SESSIONS`.
RENAME_DAYS = 5
RENAME_SESSIONS = 20
#: A change row applies once two runs at least this far apart have both read it.
CONFIRM_HOURS = 20
#: The tradable list is the union of every member of this many months (section 11).
UNION_MONTHS = 36
CHECKS = ("source", "append_only", "count", "overlap", "assets", "wiki_agreement")

_STUB = "league.ops.equity_universe is a Step 0 stub: package A builds it (league/xs/E4_INTERFACES.md)"


def web(gateway: Any, url: str, *, allow_truncated: bool = False) -> str:
    """The text of `url` through the gateway's reader. ValueError on a refusal or a non-2xx status, and on a
    `truncated` answer unless allowed."""
    raise NotImplementedError(_STUB)


def parse_spells(text: str) -> list[tuple[str, dt.date, dt.date | None]]:
    """(ticker, start, end | None) of the spell file's rows; ValueError on a malformed row."""
    raise NotImplementedError(_STUB)


def append_only(old: Sequence[tuple], new: Sequence[tuple], known_through: dt.date) -> list[str]:
    """Why a new pin's spells are not the old ones grown (an empty list: they are): a new pin may only end open spells
    after `known_through` and add spells starting after it; a difference confined to spells that ended before
    2016-01-04, which no panel session reads, is not a problem."""
    raise NotImplementedError(_STUB)


def latest_commit(gateway: Any) -> str | None:
    """The source repository's newest commit (GitHub's commits API, else the Atom feed `ATOM`), or None."""
    raise NotImplementedError(_STUB)


def wiki_changes(gateway: Any) -> dict[str, Any]:
    """{rows [{date, added, removed, reason}], reach (the oldest complete row's date), complete, revid}: the complete
    rows of the changes table (read with `allow_truncated`)."""
    raise NotImplementedError(_STUB)


def extend(spells: Sequence[tuple], rows: Sequence[Mapping[str, Any]], seen: Mapping[str, Any]) -> list[tuple]:
    """The spells with every confirmed change row after `known_through` applied (`seen`: when each row was first
    read)."""
    raise NotImplementedError(_STUB)


def exits(spells: Sequence[tuple], rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, dt.date], str]:
    """{(ticker, end): "deal" | "other" | "unknown"} for every ended spell (the change row within 5 calendar days of
    its end whose removed ticker is the spell's)."""
    raise NotImplementedError(_STUB)


def assets(gateway: Any, tickers: Sequence[str]) -> dict[str, dict[str, Any] | None]:
    """{ticker: the venue's asset row {id, status, tradable, fractionable, exchange} | None}."""
    raise NotImplementedError(_STUB)


def assign(spells: Sequence[tuple], previous: Mapping[str, Any] | None,
           joins: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """assets.json's object (D2): REF aids 1..12 in `league.xs.config.REF` order; a member asset is one or more spells
    joined by D2r (`joins`); aids from 100 up by (first spell start, ticker) at the first build, NEVER reused and never
    renumbered (`previous`: the last file; a new asset takes the next aid above them all)."""
    raise NotImplementedError(_STUB)


def membership(assets: Mapping[str, Any], days: Sequence[dt.date]) -> Any:
    """D3: bool (len(days), n_assets): some spell of the asset has start <= d and (end is null or d < end)."""
    raise NotImplementedError(_STUB)


def tradable(assets: Mapping[str, Any], day: dt.date) -> list[str]:
    """Section 11's list, sorted: every symbol that was a member on ANY session of the `UNION_MONTHS` months through
    `day` and is tradable, fractionable and unmasked today. No date is beside any of them."""
    raise NotImplementedError(_STUB)


def audit(spells: Sequence[tuple], *, previous: Sequence[tuple] | None, source: Mapping[str, Any],
          venue: Mapping[str, Any], days: Sequence[dt.date], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """{passed, checks: {name of `CHECKS`: {passed, problems, count}}} (the module docstring)."""
    raise NotImplementedError(_STUB)


def run(ctx: Any) -> dict[str, Any]:
    """The job (league/ops/context.py is the `ctx`). Its first statement is `league.xs.config.quiet(ctx.now(),
    WALL_S)`: a start that could still be working at a wall answers {"status": "skipped", "why"}."""
    raise NotImplementedError(_STUB)


__all__ = ["PIN", "REPO", "FILE", "RAW", "ATOM", "WEB", "ASSETS", "AGENT", "WALL_S", "MEMBERS_MIN", "MEMBERS_MAX",
           "ASSETS_MISSING_MAX", "RENAME_DAYS", "RENAME_SESSIONS", "CONFIRM_HOURS", "UNION_MONTHS", "CHECKS", "web",
           "parse_spells", "append_only", "latest_commit", "wiki_changes", "extend", "exits", "assets", "assign",
           "membership", "tradable", "audit", "run"]
