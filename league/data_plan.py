"""THE ALPACA DATA PLAN (release R0, Oct 19, 2026): what the House's market-data reads may ask of the plan it pays for.

The owner cancelled Alpaca's Algo Trader Plus on Oct 18, 2026; the account is on the free Basic plan since: IEX in real
time, SIP history up to 15 minutes ago, no OPRA. Measured through the gateway, 00:21-00:55Z Oct 19, 2026 (read-only
GETs; the numbers are not kept in git):

- `GET v2/stocks/snapshots?feed=sip` and `v2/stocks/quotes/latest?feed=sip`: HTTP 403 "subscription does not permit
  querying recent SIP data". The same with `feed=iex` answer (IEX's own book: its bars are one venue's).
- `GET v2/stocks/bars|quotes|trades?feed=sip`: refused the same way when `end` is later than 15 minutes ago (an end at
  now - 14 min refused, at now - 16 min answered), and A DATE-ONLY `end` IS THE END OF THAT NEW YORK DAY: 1Min bars
  with `end=2026-10-16` ran to 23:59Z that day, and `end=2026-10-18` was refused at 00:24Z Oct 19 (Oct 18 ends at
  04:00Z Oct 19 in New York) while `end=2026-10-18T23:59:59Z` answered. So an `end` of today's date, or of the day
  after a decision (the equity book's 16:20 ET fetch), is refused all day. With `end` left out the plan's own default
  answers. A start after the end is HTTP 400 "end should not be before start". `asof` answers.
- `GET v1beta1/options/...?feed=opra`: HTTP 403 "subscription does not permit querying OPRA data". `feed=indicative`
  answers: derived and delayed, never a price to trade on. Historical option bars and trades (no feed) answer.

THE RULES, each a read the plan serves instead of one it refuses; none changes WHICH past window a read asks for:

1. THE SIP WINDOW (`sip_end`, `sip_window`, `sip_params`): a SIP history read whose `end` lies later than
   `SIP_DELAY_SECONDS` (16 minutes, one more than the plan's 15) before now is sent with `end` at that instant (RFC
   3339, UTC, whole seconds); an earlier `end`, or none, is sent as it was. A date-only `end` is read as the plan reads
   it, the end of that New York day. The rows a read returns are those it returned before, but for the last 16
   minutes, which the plan cannot serve: a 1Day bar is stamped at its day's New York midnight, so the 16:20 ET daily
   fetch still holds the day's bar (its end becomes 16:04 ET, after the 16:00 close and its cross). A window that
   starts after its clamped end holds nothing the plan can serve: the live path's `bars` answers it empty without a
   request; a job's read is sent unchanged, so the plan's own refusal names it.
2. THE SNAPSHOT FEED (`PlanMarketData.stocks`): real-time snapshots read `alpaca_snapshot_feed` (league/config.json,
   "iex"), the bars `alpaca_feed` ("sip"). An IEX snapshot's `minuteBar`, `dailyBar` and `prevDailyBar` are one
   venue's and are dropped (`SNAPSHOT_BARS`): no IEX bar reaches a store, a volume reading or a program; the
   `latestQuote` and `latestTrade` stay.
3. OPTIONS OFF (`OPTIONS_OFF`, `PlanMarketData.chain`, `.contracts`): with `alpaca_option_feed` "off" every option read
   refuses at once, with no request: no chain, so no live program is asked to decide, the House's own routes
   (calibration, the House live test, the incubator, the paper proof) find no snapshot or requote and send nothing, and
   no read spends the plan's market-data allowance (200 requests a minute on Basic). An exit priced on the indicative
   feed would price a real limit on derived, delayed quotes; no real options position is open (Oct 19, 2026).

`PlanMarketData` is the live path's market data as league/service.py builds it from league/config.json; the live path's
code (league/live/, inside the options execution fingerprint) is unchanged, as it was by every feed the configuration
named before. league/ops/context.py's `Gateway` applies rule 1 to every House job's read (`sip_params`).
"""

from __future__ import annotations

import datetime as dt
import math
import re
import time
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from .live.venue import BAR_ADJUSTMENTS, MarketData, VenueError, parse_time

#: The feed whose recent data the plan withholds, and how far back a read of it may end: the plan's 15 minutes and one.
SIP = "sip"
SIP_DELAY_SECONDS = 16 * 60
#: `alpaca_option_feed` "off": the plan serves no option feed to trade on.
OFF = "off"
OPTIONS_OFF = "options market data is off (league/config.json alpaca_option_feed: the Basic plan has no OPRA)"
#: An IEX snapshot's bars (one venue's), dropped from every snapshot that is not on the bars' own feed.
SNAPSHOT_BARS = ("minuteBar", "dailyBar", "prevDailyBar")
#: A job's read the SIP window binds: the gateway's Alpaca stock history routes (never `latest` or `snapshots`).
SIP_PATH = re.compile(r"^/v1/alpaca(?:-paper)?/v2/stocks(?:/[^/?]+)?/(?:bars|quotes|trades)$")
NEW_YORK = ZoneInfo("America/New_York")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(float(epoch), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bound(value: Any, *, end: bool) -> float | None:
    """The instant a read's `start` or `end` names, epoch seconds, or None when it names none the House can read.
    RFC 3339 is its instant; a date-only END is the end of that New York day (the plan's reading, measured), and a
    date-only START its earliest reading, the UTC midnight that begins it (a window is never judged empty that the
    plan would serve)."""
    if value is None:
        return None
    text = str(value).strip()
    if _DAY.match(text):
        try:
            day = dt.date.fromisoformat(text)
        except ValueError:
            return None
        if end:
            return dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), NEW_YORK).timestamp()
        return dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp()
    return parse_time(text)


def cutoff(now: float) -> float:
    """The latest instant a SIP read may end at `now`: `SIP_DELAY_SECONDS` before it, on the whole second."""
    return float(math.floor(float(now)) - SIP_DELAY_SECONDS)


def sip_end(end: Any, *, now: float) -> Any:
    """Rule 1: `end` as the plan serves it at `now`. None stays None (the plan's own default end answers); an `end`
    at or before `cutoff(now)`, or one the House cannot read, is returned as it was; a later one (a date-only end of
    today or later, an instant inside the last 16 minutes) becomes `cutoff(now)` in RFC 3339."""
    if end is None:
        return None
    at = bound(end, end=True)
    limit = cutoff(now)
    if at is None or at <= limit:
        return end
    return _iso(limit)


def sip_window(start: Any, end: Any, *, now: float) -> tuple[Any, bool]:
    """(the `end` to send, whether the window is empty): rule 1, and EMPTY when `start` lies after the end the read
    may have (the plan would answer 400 "end should not be before start", or hold nothing)."""
    sent = sip_end(end, now=now)
    first = bound(start, end=False)
    last = cutoff(now) if sent is None else bound(sent, end=True)
    return sent, first is not None and last is not None and first > last


def sip_params(path: str, params: Mapping[str, Any] | None, *, now: float) -> Mapping[str, Any] | None:
    """Rule 1 for a House job's gateway read: `params` with `end` clamped when `path` is an Alpaca stock history route
    (`SIP_PATH`) and the read names `feed=sip`; every other read, a read with no `end`, and a window that would then be
    empty are returned unchanged (the last is refused by the plan in its own words)."""
    if not params or str(params.get("feed") or "").lower() != SIP or not SIP_PATH.match(str(path).split("?")[0]):
        return params
    if params.get("end") is None:
        return params
    sent, empty = sip_window(params.get("start"), params.get("end"), now=now)
    if empty or sent == params.get("end"):
        return params
    return {**params, "end": sent}


class PlanMarketData(MarketData):
    """The live path's market data under the plan (the module docstring): `stocks` on the snapshot feed with an IEX
    snapshot's bars dropped, `bars` on the bar feed inside the SIP window, `chain` and `contracts` refused at once with
    the option feed off. Everything else is `league.live.venue.MarketData`'s."""

    def __init__(self, client: Any, *, option_feed: str = "opra", stock_feed: str = SIP, snapshot_feed: str | None = None,
                 clock: Callable[[], float] = time.time):
        super().__init__(client, option_feed=str(option_feed), stock_feed=str(stock_feed), clock=clock)
        self.snapshot_feed = str(snapshot_feed or stock_feed)

    def stocks(self, symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
        names = sorted({str(s).upper() for s in symbols if s})
        if not names:
            return {}
        page = self._get("/v2/stocks/snapshots", {"symbols": ",".join(names), "feed": self.snapshot_feed}, "stock snapshots")
        if not isinstance(page, dict):
            raise VenueError("stock snapshots: not a map")
        if self.snapshot_feed == self.stock_feed:
            return page
        return {symbol: ({k: v for k, v in row.items() if k not in SNAPSHOT_BARS} if isinstance(row, dict) else row)
                for symbol, row in page.items()}

    def bars(self, symbols: Iterable[str], *, timeframe: str, start: str, end: str | None = None,
             adjustment: str = "raw") -> dict[str, list[dict]]:
        if self.stock_feed == SIP:
            end, empty = sip_window(start, end, now=self.clock())
            if empty:
                if adjustment not in BAR_ADJUSTMENTS:
                    raise ValueError(f"bars: adjustment {adjustment!r} is not one of {BAR_ADJUSTMENTS}")
                return {name: [] for name in sorted({str(s).upper() for s in symbols if s})}
        return super().bars(symbols, timeframe=timeframe, start=start, end=end, adjustment=adjustment)

    def chain(self, underlying: str, **kwargs: Any) -> dict[str, dict[str, Any]]:
        if self.option_feed == OFF:
            raise VenueError(f"market data chain {underlying}: {OPTIONS_OFF}")
        return super().chain(underlying, **kwargs)

    def contracts(self, symbols: Iterable[str], **kwargs: Any) -> dict[str, dict[str, Any]]:
        if self.option_feed == OFF:
            raise VenueError(f"market data contracts: {OPTIONS_OFF}")
        return super().contracts(symbols, **kwargs)


__all__ = ["PlanMarketData", "sip_end", "sip_window", "sip_params", "bound", "cutoff", "SIP", "SIP_DELAY_SECONDS", "OFF",
           "OPTIONS_OFF", "SNAPSHOT_BARS", "SIP_PATH"]
