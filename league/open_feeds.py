"""The recorders of the key-free data hosts added by the Kalshi-scale run on Sept 25-26, 2026
(docs/goals/LTCM_KALSHI_SCALE.md, workstream I2), and the rule that answers the data requests no
recorder can (workstream I3).

The owner, Sept 25, 2026: "expand the allow list incredibly broadly... everything useful there for
agents and they know they can use these online resources." Strategy boxes stay sealed -- a strategy
must behave the same in replay, practice and real money -- so the web reaches them only as recorded,
point-in-time feeds: each host here is a `Source` (league/feeds.py) whose rows live wakes and replays
read through `NEEDS["feeds"]`, under the same three rules as every feed (a row is visible only from
the moment it became knowable; a failed poll stores nothing; unchanged content is stored once).

THE RULE A HOST PASSES (the plan's I2): key-free, public, its terms permit automated access, and it
answers without a bot wall. Refused: anything behind a login, a key, a paid plan or a captcha, and
anything whose terms forbid bots, permit only personal or non-commercial use, or bar trading firms.
Every recorder's docstring names the terms it was checked against and the URL read (Sept 25, 2026).
Hosts that failed are not recorded; `REFUSALS` answers the requests that name them.

WHAT IS RECORDED (twenty-one new hosts, and Kalshi's own candles on a host already allowed):

- What the settlement stations recorded: `cli` (history; the NWS climate reports each Kalshi weather
  market settles on, as the Iowa Environmental Mesonet parses them, stamped at issue), `cli_text`
  (history as issued; the NWS's own raw report, faster), `metar` (history; every METAR, stamped at
  the Aviation Weather Center's receipt), `ghcnd` (live; NCEI's quality-checked daily summaries).
- What traded on Kalshi: `kalshi_candles` (history; every market's hourly candle, for capacity).
- Macro releases and calendars: `bls`, `fiscal`, `fomc`, `bls_releases`, `bea_releases` (live),
  `fx` (history; the ECB's reference rates), `cot` (history; the CFTC's Commitments of Traders).
- Notices: `presidential` (history; the White House's presidential actions, what KXTRUMPACT settles
  on), `federal_register` (history), `halts` (live; Nasdaq's trade halts), `fuel` (live; EIA's tables).
- Attention, hazards and crypto: `pageviews`, `fear_greed` (history), `gdelt`, `mempool`, `storms`,
  `quakes` (live).

Import order: league.feeds imports this module once `Source` and its helpers exist, and registers
`SOURCES` into `RECORDERS`; importing this module first hands the importer the module league.feeds
built (below), so either order works. Standard library only (and `ltcm.data` for the fetchers).
"""

from __future__ import annotations

import sys as _sys

if __name__ == "league.open_feeds" and "league.feeds" not in _sys.modules:  # pragma: no cover - import order
    # Imported before league.feeds, which imports this module itself (after `Source` exists) and
    # registers what it builds: let it, and become that module (a module may replace itself in
    # sys.modules; the import system hands the importer the replacement). The rest of this file then
    # runs once more to no effect.
    del _sys.modules[__name__]
    import league.feeds  # noqa: F401,E402

import math  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from functools import lru_cache  # noqa: E402
from typing import Any, Callable, Mapping, Sequence  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from .feeds import BLOCKED, NOT_LISTED, Source, _num, stamp  # noqa: E402

HOUR = 3600.0
DAY = 86400.0


# ------------------------------------------------------------------------------ small helpers
def _hour_floor(moment: float) -> float:
    return math.floor(float(moment) / HOUR) * HOUR


def _hour_ceil(moment: float) -> float:
    return math.ceil(float(moment) / HOUR) * HOUR


def _day_start(day: str, offset_hours: float) -> float:
    """Local standard midnight opening climate day `day`, as UTC epoch seconds."""
    return datetime.fromisoformat(day[:10]).replace(tzinfo=timezone.utc).timestamp() - float(offset_hours) * HOUR


def _local_day(moment: float, offset_hours: float) -> str:
    return datetime.fromtimestamp(float(moment) + float(offset_hours) * HOUR, timezone.utc).date().isoformat()


def _station_key(raw: Any) -> str | None:
    from ltcm.data.weather import station_for

    return station_for(raw)


def _stations(recorder: Any) -> list[str]:
    from .feeds import weather_stations

    return weather_stations(recorder.niches())


def _cached(recorder: Any, feed: str, slot: str, now: float, fresh: float, fetch: Callable[[], Any]) -> Any:
    """What `fetch` answered for `slot` within the last `fresh` seconds of this House's clock, else a new
    answer. A failure is remembered as well, for a minute: twenty keys that share one request must not
    ask a failing host twenty times in a pass."""
    memo = recorder.state(feed).setdefault("memo", {})
    held = memo.get(slot)
    if held is not None:
        at, value = held
        if isinstance(value, BaseException) and now - at < 60.0:
            raise value
        if not isinstance(value, BaseException) and now - at < fresh:
            return value
    try:
        value = fetch()
    except Exception as exc:  # noqa: BLE001 - remembered, then raised for this key's poll to fail
        memo[slot] = (now, exc)
        raise
    memo[slot] = (now, value)
    for old in [name for name, (at, _) in memo.items() if now - at > 6 * HOUR]:
        memo.pop(old, None)
    return value


# ------------------------------------------------------------------ weather: what was observed
class ClimateReports(Source):
    """The NWS Daily Climate Report (CLI) of each settlement station: the numbers every Kalshi daily
    high, low and rain market settles on, as the Iowa Environmental Mesonet parses them, stamped with
    the NWS product's own issue time.

    Terms (read Sept 25, 2026): https://mesonet.agron.iastate.edu/disclaimer.php -- the IEM's data "may
    be used freely by anyone for any lawful purpose", commercial use included; robots.txt asks crawlers
    for a 120 s delay and disallows neither /json/ nor /geojson/. Key-free; answered the House's
    User-Agent with JSON, no bot wall. Polled hourly: one pass reads two day files (every CLI station,
    about 0.8 MB each) that all keys share; the backfill reads each station's year file once."""

    name = "cli"
    host = "mesonet.agron.iastate.edu"
    source = ("iem: mesonet.agron.iastate.edu/geojson/cli.py?dt=<day> (every CLI station, one day) and /json/cli.py?station=<station>"
              "&year=<year> (a station's year): the NWS Daily Climate Report as the Iowa Environmental Mesonet parses it")
    cadence = ("hourly, ten minutes past the hour (the NWS issues a preliminary report in the afternoon and the final one the next "
               "morning); backfilled over the replay window")
    what = ("per settlement station, each NWS Daily Climate Report as issued -- the numbers Kalshi's daily high, low and rain markets "
            "settle on: {station, date (the climate day, local standard time), final, product, issued, high, low (F), precip_in, "
            "snow_in (0.0001 is a trace), high_time, low_time, high_normal, low_normal, precip_month_in}; final is False for a "
            "same-day preliminary report (the high so far) and True once the report was issued after the climate day ended")
    point_in_time = ("each row is stamped with the NWS product's own issue time (the timestamp in its product id) and shown only "
                     "from then on, live and in replay; the history is backfilled from the IEM's archive, which keeps the newest "
                     "report of each day (the final, or a later correction), stamped the same way -- a same-day preliminary report "
                     "exists only where the House read it live")
    history = True
    every = 3600.0
    offset = 600.0
    gap = 36 * 3600.0
    max_keys = 24
    timeout = 30.0  # per socket read; the day file is about 0.8 MB (review of #309: 45 s held the lane)
    example = "KXHIGHNY"
    note = ("The market settles on the FINAL report (final True); a preliminary one's high is the high so far. The station is the "
            "one Kalshi's rules name (KNYC is Central Park).")
    #: A live pass reads the day files (today's and yesterday's) while the newest row held is this recent;
    #: otherwise it reads the station's year file.
    RECENT = 36 * 3600.0

    def keys(self, recorder: Any) -> list[str]:
        return _stations(recorder)

    def key_of(self, raw: Any) -> str | None:
        return _station_key(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.stations import Stations

        return Stations(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return f"https://mesonet.agron.iastate.edu/json/cli.py?station={key}&year=<year>"

    @staticmethod
    def row(report: Mapping[str, Any], offset_hours: float) -> tuple[float, dict[str, Any]]:
        issued = datetime.fromisoformat(str(report["issued"]).replace("Z", "+00:00")).timestamp()
        final = issued >= _day_start(report["date"], offset_hours) + DAY
        return issued, {**report, "final": final}

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        from ltcm.data.weather import city_of_station, standard_offset_hours

        offset = standard_offset_hours(city_of_station(key))
        top = float(now) if before is None else min(float(now), float(before) - 0.001)
        newest = (recorder._load_stats().get((self.name, key)) or {}).get("last_ok") if before is None else None
        if newest is not None and now - float(newest) <= self.RECENT:
            rows = []
            for back in (1, 0):
                day = _local_day(now - back * DAY, offset)
                table = _cached(recorder, self.name, f"day:{day}", now, 600.0, lambda day=day: fetcher.cli_day(day))
                if key in table:
                    rows.append(self.row(table[key], offset))
            return {"rows": [(at, p) for at, p in rows if floor <= at <= top], "reached": True, "exhausted": False}
        year = datetime.fromtimestamp(top, timezone.utc).year
        years = [year] + ([year - 1] if datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() > floor else [])
        rows, seen = [], False
        for number in years:
            reports = fetcher.cli_year(key, number)
            seen = seen or bool(reports)
            rows.extend(self.row(report, offset) for report in reports)
        if not seen:
            from ltcm.data import DataError

            raise DataError(f"{NOT_LISTED} the IEM holds no climate report for {key} in {years}")
        rows = [(at, p) for at, p in rows if floor <= at <= top]
        return {"rows": rows, "reached": True, "exhausted": False}

    def asks(self, words: set[str]) -> bool:
        climate = bool(words & {"cli", "climate"}) and bool(words & {"report", "reports", "nws", "daily", "settlement", "settled"})
        observed = bool(words & {"observed", "actual", "actuals", "settlement", "settled", "official"}) and bool(
            words & {"high", "highs", "low", "lows", "temperature", "temperatures", "tmax", "tmin"})
        return climate or observed


class StationObservations(Source):
    """Every METAR of each settlement station -- the hourly readings (and the six- and 24-hour extremes)
    the climate report's high and low come from -- stamped when the Aviation Weather Center received it.

    Terms (read Sept 25, 2026): https://aviationweather.gov/data/api/ -- a key-free public API for
    programs; it asks for a custom User-Agent and at most 100 requests a minute ("Please keep requests
    limited in scope and frequency"); US government data. No robots.txt. Answered the House's
    User-Agent with JSON. One request a pass answers every station; the backfill reads 72 hours of one
    station a request, back to the 30 days the service holds."""

    name = "metar"
    host = "aviationweather.gov"
    source = ("awc: aviationweather.gov/api/data/metar?ids=<stations>&format=json&hours=<n>[&date=<end>] (every METAR and SPECI of "
              "the settlement stations; 30 days back)")
    cadence = "every 30 minutes, seven minutes past the hour and the half hour; backfilled 29 days (the service holds 30)"
    what = ("per settlement station, each METAR/SPECI as received: {station, observed, received, type, temp_f, dewpoint_f, max_6h_f, "
            "min_6h_f (the six-hour extremes a synoptic report carries), max_24h_f, min_24h_f, wind_dir, wind_kt, gust_kt, "
            "precip_1h_in, precip_6h_in, precip_24h_in, raw}")
    point_in_time = ("each row is stamped with the moment the Aviation Weather Center received the report (its receiptTime) and "
                     "shown only from then on, live and in replay; the 30 days the service holds are backfilled and stamped the same "
                     "way, never with when the House fetched them")
    history = True
    every = 1800.0
    offset = 420.0
    gap = 2 * 3600.0
    backfill_days = 29.0
    max_keys = 24
    timeout = 30.0
    pause = 1.0
    example = "KNYC"
    note = ("Temperatures are converted from the report's Celsius; the day's high so far is the max of temp_f and max_6h_f since "
            "local standard midnight (the CLI day). KNYC is Central Park, the station Kalshi's New York markets settle on.")
    PAGE_HOURS = 72
    #: A live pass asks this many hours for every station at once, or back to the oldest newest row held.
    HEAD_HOURS = 3

    def keys(self, recorder: Any) -> list[str]:
        return _stations(recorder)

    def key_of(self, raw: Any) -> str | None:
        return _station_key(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.stations import Stations

        return Stations(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return f"https://aviationweather.gov/api/data/metar?ids={key}&format=json&hours={self.PAGE_HOURS}&date=<end>"

    @staticmethod
    def rows(reports: Sequence[Mapping[str, Any]], key: str) -> list[tuple[float, dict[str, Any]]]:
        return [(float(r["received_at"]), {k: v for k, v in r.items() if k != "received_at"}) for r in reports if r["station"] == key]

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        if before is None:
            stats = recorder._load_stats()
            keys = list(recorder.keys(self.name)) or [key]
            behind = [now - float(stats[(self.name, k)]["last_ok"]) for k in keys
                      if (stats.get((self.name, k)) or {}).get("last_ok") is not None]
            hours = min(self.PAGE_HOURS, max([self.HEAD_HOURS] + [math.ceil(b / HOUR) + 1 for b in behind]))
            # One request a pass answers every station (the first key asks back far enough for all);
            # a failure is remembered for the pass too, so twenty keys do not ask a failing host twenty times.
            memo = recorder.state(self.name).setdefault("memo", {})
            held = memo.get("head")
            fresh = held is not None and now - held[0] < 120.0
            if fresh and isinstance(held[1], BaseException):
                raise held[1]
            if fresh and held[1][0] >= hours:
                hours, reports = held[1]
            else:
                try:
                    reports = fetcher.metars(keys, hours=hours)
                except Exception as exc:  # noqa: BLE001 - remembered, then raised: this key's poll fails
                    memo["head"] = (now, exc)
                    raise
                memo["head"] = (now, (hours, reports))
            rows = [(at, p) for at, p in self.rows(reports, key) if floor <= at <= now]
            return {"rows": rows, "reached": now - hours * HOUR <= floor, "exhausted": False}
        end = min(float(now), float(before))
        reports = fetcher.metars([key], hours=self.PAGE_HOURS, end=end)
        rows = [(at, p) for at, p in self.rows(reports, key) if floor <= at < before and at <= now]
        reached = end - self.PAGE_HOURS * HOUR <= floor
        return {"rows": rows, "reached": reached, "exhausted": not reports and not reached}

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"metar", "metars", "asos", "speci"}) or (
            bool(words & {"observation", "observations", "observed", "reading", "readings"})
            and bool(words & {"station", "stations", "weather", "temperature", "temperatures", "hourly", "intraday"}))


class DailySummaries(Source):
    """NCEI's GHCN-Daily summaries of the settlement stations -- the quality-checked daily high, low,
    precipitation and snow -- as NCEI publishes them now (about three days behind, and revised).

    Terms (read Sept 25, 2026): https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation
    and NCEI's open data policy -- the data "are in the public domain in the United States"; the
    Access Data Service needs no token; robots.txt's `Disallow: /data*` does not cover /access/services/.
    Answered the House's User-Agent with JSON. One request answers every station."""

    name = "ghcnd"
    host = "www.ncei.noaa.gov"
    source = ("ncei: www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=<GHCN ids>&dataTypes=TMAX,TMIN,PRCP,"
              "SNOW (GHCN-Daily, the last 14 days)")
    cadence = "every six hours"
    what = ("per settlement station, NCEI's GHCN-Daily summaries of the last 14 days: {station, ghcnd, latest: {date, high, low, "
            "precip_in, snow_in}, days: [...] oldest first} (F and inches; about three days behind, and revised by NCEI's checks)")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: NCEI "
                     "publishes no time a day's value appeared (and revises it), so nothing is backfilled -- the climate report "
                     "(cli) is the stamped history of the same numbers")
    batch = True
    every = 6 * 3600.0
    gap = 18 * 3600.0
    max_keys = 24
    timeout = 45.0
    example = "KNYC"
    note = "The cli feed carries the same day's numbers days earlier; ghcnd is the quality-checked record."
    DAYS = 14

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.stations import GHCND

        return [station for station in _stations(recorder) if station in GHCND]

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.stations import GHCND

        key = _station_key(raw)
        return key if key in GHCND else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.stations import Stations

        return Stations(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        from ltcm.data import DataError
        from ltcm.data.stations import GHCND

        today = datetime.fromtimestamp(now, timezone.utc).date()
        found = fetcher.daily_summaries([GHCND[k] for k in keys], (today - timedelta(days=self.DAYS)).isoformat(), today.isoformat())
        out: dict[str, Any] = {}
        for key in keys:
            days = found.get(GHCND[key]) or []
            out[key] = ({"station": key, "ghcnd": GHCND[key], "latest": days[-1], "days": days} if days
                        else DataError(f"ncei: no daily summary for {key} ({GHCND[key]}) in the last {self.DAYS} days"))
        return out

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"ghcnd", "ghcn", "ncei"}) or ("daily" in words and "summaries" in words)


# ------------------------------------------------------------- Kalshi: what traded, by the hour
def _candle_desks(niches: Mapping[str, Any]) -> list[list[str]]:
    """The universes of the open Kalshi desks whose markets are few enough to read by the hour: every
    desk but the crypto ones (an hourly strike series lists about a thousand markets a day), the sports
    and weather desks first (the desks with proven families)."""
    order = {"kalshi-sports": 0, "kalshi-weather": 1}  # the desks with proven families first
    desks = [n for n in niches.values() if getattr(n, "venue", "") == "kalshi" and not getattr(n, "dormant", False)
             and str(getattr(n, "category", "")) != "Crypto"]
    desks.sort(key=lambda n: order.get(str(getattr(n, "id", "")), 2))
    return [[str(s).upper() for s in getattr(n, "universe", ())] for n in desks]


@lru_cache(maxsize=1)
def _known_candle_series() -> frozenset[str]:
    from . import niches as niches_module

    return frozenset(s for universe in _candle_desks(niches_module.load()) for s in universe)


class KalshiCandles(Source):
    """Kalshi's own hourly candle of every market in a series the desks trade -- contracts traded, open
    interest, the traded range and the yes bid and ask at the hour's close -- for workstream K2's
    capacity curves (what trades at a price, per hour, around a family's own fills). A candle is final
    when its hour ends, and Kalshi stamps it with that end.

    Public market data on a host already on the allowlist (api.elections.kalshi.com); no key. The trade
    tape was measured and set aside (ltcm/data/kalshi_candles.py): 6,000 prints a minute. A page reads a
    day of one series: its markets (one request) and their candles (one request per hundred markets)."""

    name = "kalshi_candles"
    host = "api.elections.kalshi.com"
    source = ("kalshi: api.elections.kalshi.com/trade-api/v2/markets?series_ticker=<series> and /markets/candlesticks?market_tickers="
              "<up to 100>&period_interval=60 (hourly candles)")
    cadence = "hourly, four minutes past the hour; backfilled 14 days"
    what = ("per Kalshi series the desks trade (crypto strike series excluded: a thousand markets a day), one row an hour: {series, "
            "hour_start, volume (contracts traded in the series' markets read), markets_traded, markets_read, markets_listed, "
            "markets: {ticker: {volume, open_interest, open, high, low, close (traded YES price, dollars; None in an hour without "
            "a trade), bid, ask (YES bid and ask at the hour's close)}}} -- a market is in `markets` for an hour it had a candle")
    point_in_time = ("each row is an hour of Kalshi's candles stamped when the hour ENDED (Kalshi's end_period_ts) and shown only "
                     "from then on, live and in replay; the history is backfilled from Kalshi's own candles and stamped the same "
                     "way, and the hour still running is never stored")
    history = True
    every = 3600.0
    offset = 240.0
    gap = 2 * 3600.0
    backfill_days = 14.0
    max_keys = 16
    timeout = 20.0
    pause = 0.3
    example = "KXMLBGAME"
    note = ("markets_listed counts the series' markets open during the hour (by their listing times), markets_read those of them "
            "read; fewer read means a series listed more than 300 and the busiest (by volume up to when the hour was fetched) were "
            "read. An hour with no row is not recorded, an hour whose row has no markets had no activity in the markets read.")
    WINDOW_HOURS = 24
    MAX_MARKETS = 300
    #: A market closing this long after an hour can still have traded in it (an MLB game's closes days later).
    CLOSE_AFTER_DAYS = 10

    def keys(self, recorder: Any) -> list[str]:
        """Round robin over the desks' universes (busiest series first in each), sports and weather first."""
        universes = _candle_desks(recorder.niches())
        out: list[str] = []
        for rank in range(max((len(u) for u in universes), default=0)):
            for universe in universes:
                if rank < len(universe) and universe[rank] not in out:
                    out.append(universe[rank])
        return out

    def key_of(self, raw: Any) -> str | None:
        text = str(raw or "").strip().upper()
        return text if text in _known_candle_series() else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.kalshi_candles import KalshiCandles as Client

        return Client(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return f"https://api.elections.kalshi.com/trade-api/v2/markets/candlesticks?market_tickers=<{key} markets>&period_interval=60"

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        from ltcm.data.kalshi_candles import MAX_BATCH

        last = _hour_floor(now if before is None else min(float(now), float(before) - 0.001))  # the newest hour end asked for
        first = _hour_ceil(floor)
        if last < first:
            return {"rows": [], "reached": True, "exhausted": False}
        top_first = max(first, last - (self.WINDOW_HOURS - 1) * HOUR)  # the page's oldest hour end
        opened = top_first - HOUR
        listed = [m for m in fetcher.markets(key, closing_from=opened, closing_to=last + self.CLOSE_AFTER_DAYS * DAY)
                  if m["open"] is not None and m["open"] < last]
        markets = sorted((m for m in listed if m["volume"] > 0), key=lambda m: -m["volume"])
        chosen = markets[:self.MAX_MARKETS]
        read = [m["ticker"] for m in chosen]

        def open_in(pool: Sequence[Mapping[str, Any]], end: float) -> int:
            # Per hour, from listing times alone (review of #309, Sept 25, 2026): a count over the whole page
            # counted markets listed later that day, and lifetime volume says which markets trade after the hour.
            return sum(1 for m in pool if m["open"] < end and (m["close"] is None or m["close"] > end - HOUR))
        candles: dict[str, list[dict[str, Any]]] = {}
        for index in range(0, len(read), MAX_BATCH):
            candles.update(fetcher.candles(read[index:index + MAX_BATCH], opened, last))
        by_hour: dict[float, dict[str, Any]] = {}
        for ticker, rows in candles.items():
            for candle in rows:
                end = float(candle["end"])
                if top_first <= end <= last and end <= now:
                    by_hour.setdefault(end, {})[ticker] = {
                        "volume": candle["volume"], "open_interest": candle["open_interest"], "open": candle["open"],
                        "high": candle["high"], "low": candle["low"], "close": candle["close"], "bid": candle["bid_close"],
                        "ask": candle["ask_close"]}
        rows_out = []
        hour = top_first
        while hour <= last:
            markets_now = by_hour.get(hour, {})
            rows_out.append((hour, {"series": key, "hour_start": stamp(hour - HOUR), "volume": round(sum(m["volume"] for m in markets_now.values()), 2),
                                    "markets_traded": sum(1 for m in markets_now.values() if m["volume"] > 0),
                                    "markets_read": open_in(chosen, hour), "markets_listed": open_in(listed, hour),
                                    "markets": markets_now}))
            hour += HOUR
        return {"rows": rows_out, "reached": top_first <= first, "exhausted": False}

    def asks(self, words: set[str]) -> bool:
        kalshi = "kalshi" in words or any(w.startswith("kx") for w in words)
        return kalshi and bool(words & {"candle", "candles", "candlestick", "candlesticks", "volume", "volumes", "capacity", "prints",
                                        "trades", "traded", "liquidity", "hourly", "ohlc"}) \
            and not words & {"orderbook", "book", "depth", "fills", "fill", "outcome", "outcomes"}


# ====================================================================================================
# The macro releases: BLS, FiscalData, the ECB, the CFTC, the Fed.
# ====================================================================================================
_FFT = ZoneInfo("Europe/Berlin")


# ---------------------------------------------------------------------------------------- BLS
class BlsSeries(Source):
    """The Bureau of Labor Statistics' published series that Kalshi's economics markets settle on --
    CPI (headline, core, not seasonally adjusted), the unemployment rate, payrolls, average hourly
    earnings, PPI -- as BLS's public data API answers now.

    Terms (read Sept 25, 2026): https://www.bls.gov/developers/ and
    https://www.bls.gov/developers/termsOfService.htm -- version 1 of the API needs no registration (25
    queries a day, 25 series a query; https://www.bls.gov/developers/api_faqs.htm) and nothing in the
    terms bars automated use; the API host's robots.txt (`Disallow: /`) is a crawler rule for a host
    that exists only for programs. Answered the House's User-Agent with JSON. ONE query (a POST that
    only reads) answers every series; polled every 90 minutes -- 16 of the 25 daily queries, the rest
    left for restarts. BLS's own answer that the day's queries are spent is recorded as `BLOCKED` (asked
    again at the next cadence, never every five minutes)."""

    name = "bls"
    host = "api.bls.gov"
    source = ("bls: api.bls.gov/publicAPI/v1/timeseries/data/ (one query for CUSR0000SA0, CUSR0000SA0L1E, CUUR0000SA0, "
              "LNS14000000, CES0000000001, CES0500000003, WPSFD4; no key: 25 queries a day)")
    cadence = "every 90 minutes (BLS releases at 08:30 ET; the keyless API allows 25 queries a day)"
    what = ("per series (CPI, CPI_CORE, CPI_NSA, UNRATE, PAYROLLS, AHE, PPI), what BLS has published: {series_id, latest: "
            "{period (YYYY-MM), value, period_name, latest, preliminary}, change_1m_pct, change_12m_pct, diff_1m (the change in "
            "the series' own units: thousands of jobs for PAYROLLS, points for UNRATE), recent: the 13 newest months}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: BLS "
                     "publishes no time a value appeared (its releases are at 08:30 ET), so nothing is backfilled; a revision "
                     "is a new row")
    batch = True
    every = 5400.0
    gap = 3 * 5400.0
    timeout = 30.0
    #: A failed query is asked again after 45 minutes, not five: 25 keyless queries a day (review of #309).
    retry = 2700.0
    example = "CPI"
    note = ("CPI is seasonally adjusted (Kalshi's monthly CPI markets); CPI_NSA is the index the year-over-year markets settle "
            "on. A preliminary value (payrolls, earnings, PPI) is revised in later months.")
    ALIASES = {"KXCPI": "CPI", "HEADLINE": "CPI", "CPIU": "CPI", "KXCPICORE": "CPI_CORE", "CORE": "CPI_CORE", "CORECPI": "CPI_CORE",
               "KXCPICOREYOY": "CPI_CORE", "KXCPIYOY": "CPI_NSA", "CPIYOY": "CPI_NSA", "KXU3": "UNRATE", "U3": "UNRATE",
               "UNEMPLOYMENT": "UNRATE", "KXPAYROLLS": "PAYROLLS", "NFP": "PAYROLLS", "NONFARM": "PAYROLLS", "JOBS": "PAYROLLS",
               "EARNINGS": "AHE", "WAGES": "AHE", "KXPPI": "PPI"}

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.releases import BLS_SERIES

        return list(BLS_SERIES)

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.releases import BLS_SERIES

        text = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
        by_id = {series: name for name, series in BLS_SERIES.items()}
        text = by_id.get(text, self.ALIASES.get(text.replace("_", ""), self.ALIASES.get(text, text)))
        return text if text in BLS_SERIES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.releases import Releases

        return Releases(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        from ltcm.data import DataError
        from ltcm.data.releases import BLS_SERIES, bls_summary

        try:
            found = fetcher.bls([BLS_SERIES[key] for key in keys])
        except DataError as exc:
            if "threshold" in str(exc).lower() or "daily" in str(exc).lower():  # BLS: the day's 25 queries are spent
                raise DataError(f"{BLOCKED} {exc}") from exc
            raise
        out: dict[str, Any] = {}
        for key in keys:
            rows = found.get(BLS_SERIES[key]) or []
            try:
                out[key] = {"key": key, **bls_summary(BLS_SERIES[key], rows)}
            except DataError as exc:
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        if words & {"nowcast", "nowcasting", "forecast", "forecasts", "consensus", "expectation", "expectations", "estimate",
                    "estimates", "calendar", "schedule", "surprise"}:
            return False
        return "bls" in words or bool(words & {"cpi", "payrolls", "nonfarm", "nfp", "ppi", "unemployment", "u3"})


# ---------------------------------------------------------------------------------- FiscalData
class TreasuryFiscal(Source):
    """The Treasury's own daily cash (the Treasury General Account on the Daily Treasury Statement),
    Debt to the Penny, and its auctions -- announced (upcoming) and with their results (high yield,
    bid-to-cover, indirect share) -- from FiscalData.

    Terms (read Sept 25, 2026): https://fiscaldata.treasury.gov/api-documentation/ -- the API "does not
    require a user account or registration for a token"; the data may be used "for non-commercial or
    commercial purposes" (https://www.treasurydirect.gov/legal-information/developers/web-api-terms/);
    fiscaldata.treasury.gov's robots.txt allows everything. Answered the House's User-Agent with JSON.
    Three requests a poll (one a key), every three hours."""

    name = "fiscal"
    host = "api.fiscaldata.treasury.gov"
    source = ("fiscaldata: api.fiscaldata.treasury.gov/services/api/fiscal_service v1/accounting/dts/operating_cash_balance, "
              "v2/accounting/od/debt_to_penny, v1/accounting/od/auctions_query")
    cadence = "every three hours (the Daily Treasury Statement is published about 16:00 ET the next business day)"
    what = ("tga: the newest Daily Treasury Statement's Treasury General Account {record_date, opening, closing, deposits, "
            "withdrawals (millions of dollars), days: [{date, closing}]}; debt: Debt to the Penny {record_date, total, "
            "held_by_public, intragovernmental (dollars), change_1d, days}; auctions: {upcoming: announced auctions without a "
            "result, recent: auctions with their result -- each {cusip, type, term, reopening, announced, auction_date, "
            "issue_date, closing_time, offering_bn, high_yield, high_discount_rate, high_investment_rate, bid_to_cover, "
            "accepted_bn, indirect_pct, direct_pct, dealer_pct}}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: FiscalData "
                     "carries a record date, never the moment a record appeared, so nothing is backfilled")
    every = 3 * 3600.0
    gap = 9 * 3600.0
    timeout = 30.0
    example = "auctions"
    note = "record_date is the business day a statement covers; it is published the next business day."
    KEYS = ("tga", "debt", "auctions")
    ALIASES = {"tga": "tga", "dts": "tga", "cash": "tga", "treasury_general_account": "tga", "debt": "debt",
               "debt_to_the_penny": "debt", "debt_to_penny": "debt", "national_debt": "debt", "auctions": "auctions",
               "auction": "auctions", "treasury_auctions": "auctions"}

    def keys(self, recorder: Any) -> list[str]:
        return list(self.KEYS)

    def key_of(self, raw: Any) -> str | None:
        return self.ALIASES.get(str(raw or "").strip().lower().replace(" ", "_").replace("-", "_"))

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.releases import Releases

        return Releases(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        out: dict[str, Any] = {}
        for key in keys:
            try:
                if key == "tga":
                    out[key] = fetcher.tga()
                elif key == "debt":
                    out[key] = fetcher.debt()
                else:
                    found = fetcher.auctions()
                    out[key] = {"upcoming": found["upcoming"][:12], "recent": found["recent"][:12]}
            except Exception as exc:  # noqa: BLE001 - one dataset that fails is a failed poll of that key
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        treasury = bool(words & {"treasury", "treasuries", "ust", "bill", "bills", "note", "notes", "bond", "bonds"})
        return bool(words & {"tga", "dts", "fiscaldata"}) or ("debt" in words and bool(words & {"penny", "national", "federal", "public"})) \
            or (bool(words & {"auction", "auctions"}) and treasury) or {"treasury", "general", "account"} <= words


# ----------------------------------------------------------------------------------------- ECB
def _fx_stamp(day: str) -> float:
    """17:00 Frankfurt time on `day`: the ECB publishes "around 16:00 CET", and an hour is allowed for it."""
    return datetime.fromisoformat(day).replace(hour=17, tzinfo=_FFT).timestamp()


class EcbReferenceRates(Source):
    """The ECB's euro foreign exchange reference rates, one row a currency a TARGET business day, as
    history: the fixing of every major currency, for Kalshi's daily EUR/USD and USD/JPY series.

    Terms (read Sept 25, 2026): https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html --
    "users of this website may make free use of the information obtained directly from it", reproduced
    accurately and citing the ECB; the rates are "published for information purposes only" (an input
    to a model, never a transaction price). robots.txt does not disallow /stats/eurofxref/ and asks for
    five seconds between requests; key-free, answered the House's User-Agent with XML. One request a
    poll, hourly."""

    name = "fx"
    host = "www.ecb.europa.eu"
    source = ("ecb: www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml (the newest day) and eurofxref-hist-90d.xml (the "
              "history): the euro reference rates, units of each currency per euro")
    cadence = "hourly, twenty minutes past the hour (published about 16:00 CET each TARGET business day); backfilled 75 days"
    what = ("per currency (USD, JPY, GBP, CHF, CAD, AUD, CNY, MXN; any of the ECB's 29), each business day's reference rate: {currency, "
            "date, per_eur (units per euro), per_usd (units per US dollar, the cross through the day's USD rate; None for USD), "
            "change_1d_pct, change_5d_pct (of per_eur), usd_change_1d_pct (of per_usd), from rows at or before it}")
    point_in_time = ("each row is stamped 17:00 Frankfurt time on its date -- the ECB publishes 'around 16:00 CET' and an hour is "
                     "allowed -- or at the file's Last-Modified when that is later the same day; shown only from then on, live and "
                     "in replay, and a day is stored only once its stamp has passed; the history is backfilled from the ECB's 90-day "
                     "file and stamped the same way")
    history = True
    every = 3600.0
    offset = 1200.0
    gap = 4 * DAY  # a weekend and a holiday between two fixings
    lookback_days = 8
    backfill_days = 75.0
    max_keys = 30
    timeout = 30.0
    example = "USD"
    note = ("The ECB publishes rates for information only; Kalshi's FX series settle on their own sources. per_usd of JPY is "
            "USD/JPY; 1/per_eur of USD is EUR per dollar.")
    DEFAULT = ("USD", "JPY", "GBP", "CHF", "CAD", "AUD", "CNY", "MXN")
    CURRENCIES = frozenset(("USD", "JPY", "CZK", "DKK", "GBP", "HUF", "PLN", "RON", "SEK", "CHF", "ISK", "NOK", "TRY", "AUD", "BRL",
                            "CAD", "CNY", "HKD", "IDR", "ILS", "INR", "KRW", "MXN", "MYR", "NZD", "PHP", "SGD", "THB", "ZAR"))
    #: The daily file is read while the newest row held is this recent; else the 90-day file.
    RECENT = 26 * 3600.0

    def keys(self, recorder: Any) -> list[str]:
        return list(self.DEFAULT)

    def key_of(self, raw: Any) -> str | None:
        text = str(raw or "").strip().upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
        text = text[2:] if text.startswith("KX") else text
        if len(text) == 6:
            base, quote = text[:3], text[3:]
            text = quote if base == "EUR" else base if quote in ("EUR", "USD") and base != "USD" else quote if base == "USD" else ""
        return text if text in self.CURRENCIES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.fx import Ecb

        return Ecb(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return f"https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml ({key} per euro)"

    @staticmethod
    def rows(days: Mapping[str, Mapping[str, float]], modified: float | None, key: str) -> list[tuple[float, dict[str, Any]]]:
        newest = max(days) if days else None
        out = []
        for day, rates in days.items():
            if key not in rates:
                continue
            at = _fx_stamp(day)
            if day == newest and modified is not None and datetime.fromtimestamp(modified, _FFT).date().isoformat() == day:
                at = max(at, modified)  # published late that day: stamped when the file changed
            usd = rates.get("USD")
            per_usd = round(rates[key] / usd, 6) if usd and key != "USD" else None
            out.append((at, {"currency": key, "date": day, "per_eur": rates[key], "per_usd": per_usd}))
        return sorted(out)

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        from ltcm.data import DataError

        if key not in self.CURRENCIES:
            raise DataError(f"{NOT_LISTED} the ECB publishes no reference rate for {key}")
        newest = (recorder._load_stats().get((self.name, key)) or {}).get("last_ok") if before is None else None
        daily = newest is not None and now - float(newest) <= self.RECENT
        days, modified = _cached(recorder, self.name, "daily" if daily else "90d", now, 300.0,
                                 fetcher.daily if daily else fetcher.last_90_days)
        rows = self.rows(days, modified, key)
        oldest = min((at for at, _ in rows), default=None)
        rows = [(at, p) for at, p in rows if floor <= at <= now and (before is None or at < before)]
        reached = daily or (oldest is not None and oldest <= floor)
        return {"rows": rows, "reached": reached, "exhausted": before is not None and not reached}

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        out = []
        values = [(p.get("per_eur"), p.get("per_usd")) for _, p in rows]

        def pct(now_value: Any, then_value: Any) -> float | None:
            return round((now_value / then_value - 1.0) * 100.0, 4) if now_value is not None and then_value else None

        for index, (at, payload) in enumerate(rows):
            eur, usd = values[index]
            one = values[index - 1] if index >= 1 else (None, None)
            five = values[index - 5] if index >= 5 else (None, None)
            out.append((at, {**payload, "change_1d_pct": pct(eur, one[0]), "change_5d_pct": pct(eur, five[0]),
                             "usd_change_1d_pct": pct(usd, one[1])}))
        return out

    def asks(self, words: set[str]) -> bool:
        if words & {"ecb", "eurofxref"}:
            return True
        pair = bool(words & {"fx", "forex", "eurusd", "usdjpy", "gbpusd", "usdcad", "audusd", "usdchf", "currency", "currencies"}) or \
            {"exchange", "rate"} <= words or {"exchange", "rates"} <= words
        return pair and bool(words & {"rate", "rates", "reference", "fixing", "fixings", "daily", "history", "historical", "euro"})



# ---------------------------------------------------------------------------------------- CFTC
class CommitmentsOfTraders(Source):
    """The CFTC's weekly Commitments of Traders (legacy, futures only) for the markets beside the
    desks' -- CME bitcoin, the E-mini S&P 500, the 10-year note, gold, WTI crude and the euro: open
    interest and the speculators' (non-commercial) and hedgers' (commercial) long, short and net.

    Terms (read Sept 25, 2026): https://www.cftc.gov/WebPolicy/index.htm -- "Government information at
    the CFTC website is in the public domain"; the Socrata API on publicreporting.cftc.gov is used without
    an app token ("As long as you are not overusing the API, you should be able to use the API without a
    token", dev.socrata.com/docs/app-tokens.html) and robots.txt allows /resource/ with a one-second
    crawl delay. Answered the House's User-Agent with JSON. One request a market a pass, a second apart.

    The stamp is the whole of its honesty: a report's positions are as of a Tuesday and the CFTC
    releases it that Friday at 15:30 ET -- the following Monday in a holiday week -- and publishes no
    release time in the data. A report is stamped seven days after its as-of date, 00:00 UTC (Monday
    evening in New York, after the latest regular release), and stored only once that has passed; a
    report the House first sees more than twelve hours after that stamp (published late, as during the
    2025 shutdown, or the House was away) is stamped when the House received it."""

    name = "cot"
    host = "publicreporting.cftc.gov"
    source = ("cftc: publicreporting.cftc.gov/resource/6dca-aqww.json (Commitments of Traders, legacy, futures only) per CFTC "
              "contract market code")
    cadence = "every six hours; a weekly report is stored once its stamp passes (the Tuesday after its as-of Tuesday); backfilled"
    what = ("per market (BTC: CME bitcoin, ES: E-mini S&P 500, TY: 10-year note, GOLD, WTI, EUR: euro FX), each weekly report: {as_of "
            "(the Tuesday the positions are as of), code, market, open_interest, change_open_interest, noncommercial: {long, short, "
            "spread, net, change_long, change_short, pct_oi_long, pct_oi_short}, commercial: {long, short, net}, nonreportable: "
            "{long, short}, traders, net_change_1w (the non-commercial net against the report before it)}")
    point_in_time = ("each row is stamped seven days after its as-of Tuesday, 00:00 UTC -- after the CFTC's Friday 15:30 ET release "
                     "and the Monday release of a holiday week -- and shown only from then on, live and in replay; a report first "
                     "seen more than twelve hours after that is stamped when the House received it; the history is backfilled from "
                     "the CFTC's own reports and stamped by the same rule")
    history = True
    every = 6 * 3600.0
    offset = 900.0
    gap = 8 * DAY
    lookback_days = 8
    max_keys = 12
    timeout = 30.0
    pause = 1.0
    example = "BTC"
    note = "Weekly: a report's positions are as of its Tuesday; net = long - short; the stamp trails the release by about three days."
    LAG = 7 * DAY
    LATE = 12 * 3600.0
    PAGE = 30
    ALIASES = {"BITCOIN": "BTC", "XBT": "BTC", "133741": "BTC", "SPX": "ES", "SP500": "ES", "S&P500": "ES", "EMINI": "ES",
               "13874A": "ES", "10Y": "TY", "UST10Y": "TY", "TNOTE": "TY", "ZN": "TY", "043602": "TY", "GC": "GOLD",
               "XAU": "GOLD", "088691": "GOLD", "CL": "WTI", "CRUDE": "WTI", "OIL": "WTI", "067651": "WTI", "EURUSD": "EUR",
               "6E": "EUR", "EUROFX": "EUR", "099741": "EUR"}

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.releases import COT_MARKETS

        return list(COT_MARKETS)

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.releases import COT_MARKETS

        text = str(raw or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "").replace("/", "")
        text = self.ALIASES.get(text, text)
        return text if text in COT_MARKETS else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.releases import Releases

        return Releases(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        from ltcm.data.releases import COT_MARKETS

        return f"https://publicreporting.cftc.gov/resource/6dca-aqww.json?cftc_contract_market_code={COT_MARKETS.get(key, key)}"

    def stamp_of(self, as_of: str) -> float:
        return datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc).timestamp() + self.LAG

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        from ltcm.data.releases import COT_MARKETS

        newest = (recorder._load_stats().get((self.name, key)) or {}).get("last_ok") if before is None else None
        since = datetime.fromtimestamp(float(floor) - self.LAG, timezone.utc).date().isoformat()
        until = datetime.fromtimestamp(float(before) - self.LAG, timezone.utc).date().isoformat() if before is not None else None
        reports = fetcher.cot(COT_MARKETS[key], since=since, before=until, limit=self.PAGE)
        rows = []
        for report in reports:
            at = self.stamp_of(report["as_of"])
            if newest is not None and at > float(newest) and now - at > self.LATE:
                at = float(now)  # first seen long after its stamp: published late, or the House was away
            if at <= now and at >= floor and (before is None or at < before):
                rows.append((at, report))
        reached = len(reports) < self.PAGE
        return {"rows": rows, "reached": reached, "exhausted": not reports and not reached}

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        out = []
        prior = None
        for at, payload in rows:
            net = (payload.get("noncommercial") or {}).get("net")
            out.append((at, {**payload, "net_change_1w": round(net - prior, 2) if net is not None and prior is not None else None}))
            prior = net if net is not None else prior
        return out

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"cot", "cftc"}) or {"commitments", "traders"} <= words or (
            bool(words & {"speculative", "speculators", "noncommercial", "commercials"}) and bool(words & {"positioning", "positions", "futures"}))


# ------------------------------------------------------------------------------------ the Fed
class FedCalendar(Source):
    """The Federal Reserve Board's calendar: the FOMC's meetings (the decision day at 2:00 p.m.), its
    minutes and press conferences, the Board's speeches and testimony, and the Beige Book -- the
    schedule Kalshi's KXFED and the Fed "mention" markets trade around.

    Terms (read Sept 25, 2026): https://www.federalreserve.gov/disclaimer.htm -- "information on Board's
    website is in the public domain and may be copied and distributed without permission"; no
    robots.txt (404). The calendar is the JSON the Board's own pages read (undocumented: it can change
    shape, and a changed shape is a failed poll). Answered the House's User-Agent. One request (about
    0.5 MB) answers every key, every twelve hours."""

    name = "fomc"
    host = "www.federalreserve.gov"
    source = "fed: www.federalreserve.gov/json/calendar.json (the Board's calendar of FOMC meetings, speeches, testimony, releases)"
    cadence = "every twelve hours"
    what = ("per kind -- fomc (meetings, minutes, press conferences), speeches, testimony, beige (the Beige Book) -- the Board's "
            "calendar from today on: {kind, next (the first event), next_meeting (fomc only: the next 'FOMC Meeting', the "
            "decision day), events: the 12 soonest [{date, end_date, title, type, time (ET), description, link}]}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: the "
                     "calendar carries no time an entry was added, so nothing is backfilled; a moved meeting is a new row")
    batch = True
    every = 12 * 3600.0
    gap = 36 * 3600.0
    timeout = 30.0
    example = "fomc"
    note = "Times are Eastern; an FOMC decision is announced at the meeting's 'time' on its end_date."
    KEYS = ("fomc", "speeches", "testimony", "beige")
    ALIASES = {"fomc": "fomc", "fed": "fomc", "kxfed": "fomc", "meetings": "fomc", "fed_meetings": "fomc", "speeches": "speeches",
               "speech": "speeches", "fed_speeches": "speeches", "testimony": "testimony", "beige": "beige", "beige_book": "beige"}

    def keys(self, recorder: Any) -> list[str]:
        return list(self.KEYS)

    def key_of(self, raw: Any) -> str | None:
        return self.ALIASES.get(str(raw or "").strip().lower().replace(" ", "_").replace("-", "_"))

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.releases import Releases

        return Releases(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        calendar = fetcher.calendar()
        out: dict[str, Any] = {}
        for key in keys:
            events = calendar.get(key) or []
            row: dict[str, Any] = {"kind": key, "next": events[0] if events else None, "events": events[:12]}
            if key == "fomc":
                row["next_meeting"] = next((e for e in events if e["title"].lower().startswith("fomc meeting")), None)
            out[key] = row
        return out

    def asks(self, words: set[str]) -> bool:
        fed = bool(words & {"fed", "federal", "fomc", "powell"})
        return "fomc" in words or (fed and bool(words & {"calendar", "meeting", "meetings", "speech", "speeches", "testimony", "beige",
                                                          "minutes", "schedule", "dates"}))


# ====================================================================================================
# The signals: attention, hazards, the bitcoin network and mood.
# ====================================================================================================
#: The attention vocabulary: a key -> (its English Wikipedia title, the other names a strategy may use:
#: a Kalshi series whose subject it is, a ticker, the plain title). The crypto desks' coins, the AI
#: share markets (KXANTHSHARE, KXOPENSHARE, KXDEEPSHARE, KXGOOGSHARE; KXTOKENUSE settles on
#: OpenRouter's rankings), the attention desk's president and his platform, and the macro words the
#: rates desks trade on. Titles checked against Wikimedia on Sept 25, 2026 (each answered views).
ATTENTION: dict[str, tuple[str, tuple[str, ...]]] = {
    "bitcoin": ("Bitcoin", ("btc", "xbt", "kxbtcd", "kxbtc")),
    "ethereum": ("Ethereum", ("eth", "ether", "kxethd", "kxeth")),
    "solana": ("Solana_(blockchain_platform)", ("sol", "kxsold", "kxsol")),
    "xrp": ("XRP_Ledger", ("ripple", "kxxrpd", "kxxrp")),
    "dogecoin": ("Dogecoin", ("doge", "kxdoged", "kxdoge")),
    "stablecoin": ("Stablecoin", ("stablecoins",)),
    "tether": ("Tether_(cryptocurrency)", ("usdt",)),
    "anthropic": ("Anthropic", ("kxanthshare",)),
    "claude": ("Claude_(language_model)", ("claude_ai",)),
    "openai": ("OpenAI", ("kxopenshare",)),
    "chatgpt": ("ChatGPT", ()),
    "deepseek": ("DeepSeek", ("kxdeepshare",)),
    "gemini": ("Google_Gemini", ("kxgoogshare",)),
    "grok": ("Grok_(chatbot)", ("xai",)),
    "openrouter": ("OpenRouter", ("kxtokenuse",)),
    "trump": ("Donald_Trump", ("kxtrumpsay", "kxtrumpact", "kxtrumpapprove")),
    "truth_social": ("Truth_Social", ("kxtruthsocial", "truthsocial")),
    "fed": ("Federal_Reserve", ("fomc", "kxfed", "federal_reserve_system")),
    "inflation": ("Inflation", ("cpi", "kxcpi")),
    "recession": ("Recession", ("kxrecession",)),
}
#: GDELT's queries, a subset of the vocabulary (one request each, at most one every six seconds).
GDELT_QUERIES: dict[str, str] = {
    "bitcoin": "bitcoin", "ethereum": "ethereum", "anthropic": "anthropic", "openai": "openai", "trump": "trump",
    "fed": '"federal reserve"', "inflation": "inflation", "recession": "recession",
}


def _normal(raw: Any) -> str:
    return "_".join(str(raw or "").strip().lower().replace("-", " ").replace("/", " ").split())


def attention_key(raw: Any, allowed: Sequence[str] | None = None) -> str | None:
    """The attention key a strategy names by key (`bitcoin`), alias (`BTC`, `KXANTHSHARE`) or Wikipedia title
    (`Donald Trump`, `Claude (language model)`); None for anything else."""
    text = _normal(raw)
    if not text or len(text) > 64:
        return None
    for key, (title, aliases) in ATTENTION.items():
        if text == key or text in aliases or text == title.lower():
            return key if allowed is None or key in allowed else None
    return None


def _utc_day(moment: float) -> date:
    return datetime.fromtimestamp(float(moment), timezone.utc).date()


def _midnight(day: date) -> float:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()


# ------------------------------------------------------------------------------ Wikipedia pageviews
class Pageviews(Source):
    """English Wikipedia's daily pageviews (human readers, every access method) of the articles whose
    subjects the desks trade: an attention underlying a strategy can replay at once.

    Terms (read Sept 25, 2026): Wikimedia's analytics data is CC0; scripted clients must send an
    informative User-Agent with a contact or "may be blocked without notice"
    (https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy), and the API usage guidelines
    (https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines) allow such a
    client 200 requests a minute, one at a time. No robots.txt rule covers /api/rest_v1/. The House's
    contact User-Agent was answered with JSON. A pass asks one request per article, half a second apart.

    The stamp: Wikimedia publishes no moment a day's count appeared. Probed Sept 25, 2026 at 06:55Z,
    Sept 24's views were already served -- under seven hours after the day ended -- but one probe is not
    a bound, and Wikimedia promises no publication time. So a day's row is stamped at the day's END plus
    24 hours (day D at D+2 00:00 UTC), by the same rule live and in the backfill: late, never early."""

    name = "pageviews"
    host = "wikimedia.org"
    source = ("wikimedia: wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/<title>/daily/"
              "<start>/<end> (English Wikipedia, human readers)")
    cadence = "every six hours, half past 00, 06, 12 and 18 UTC; backfilled over the replay window"
    what = ("per subject (bitcoin, ethereum, solana, xrp, dogecoin, stablecoin, tether, anthropic, claude, openai, chatgpt, deepseek, "
            "gemini, grok, openrouter, trump, truth_social, fed, inflation, recession: its English Wikipedia article), one row a UTC "
            "day: {article, date, views, avg_7d (the mean of the seven days before), ratio_7d (views over avg_7d)}")
    point_in_time = ("each row is a UTC day's pageviews stamped at the day's end plus 24 hours (day D at D+2 00:00 UTC: Wikimedia "
                     "publishes no moment a count appeared, and had served Sept 24's by 06:55Z the next morning, so the stamp is "
                     "late, never early) and shown only from then on, live and in replay; the history is backfilled from "
                     "Wikimedia's own record and stamped the same way, and avg_7d and ratio_7d read only days before it")
    history = True
    every = 6 * 3600.0
    offset = 1800.0
    gap = 25 * 3600.0
    lookback_days = 8
    max_keys = 20
    timeout = 20.0
    pause = 0.5
    example = "bitcoin"
    note = ("A key is also named by its Kalshi series (KXANTHSHARE -> anthropic, KXTOKENUSE -> openrouter, KXTRUTHSOCIAL -> "
            "truth_social) or its title. avg_7d and ratio_7d are None until seven earlier days are held.")
    #: The days one request asks for (Wikimedia answers a range of any length).
    PAGE_DAYS = 120
    #: A day's row is stamped this long after the day ended.
    ALLOWANCE = DAY

    def keys(self, recorder: Any) -> list[str]:
        return list(ATTENTION)

    def key_of(self, raw: Any) -> str | None:
        return attention_key(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.signals import Signals

        return Signals(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{ATTENTION[key][0]}"
                "/daily/<start>/<end>")

    def stamp_of(self, day: date) -> float:
        """Day D's row: the day's end (D+1 00:00 UTC) plus `ALLOWANCE`."""
        return _midnight(day) + DAY + self.ALLOWANCE

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        top = float(now) if before is None else min(float(now), float(before) - 0.001)
        last = _utc_day(top - DAY - self.ALLOWANCE)  # the newest day whose stamp is at or before top
        first = _utc_day(float(floor) - DAY - self.ALLOWANCE)
        if self.stamp_of(first) < floor:
            first += timedelta(days=1)
        if before is None:
            newest = (recorder._load_stats().get((self.name, key)) or {}).get("last_ok")
            if newest is not None:
                first = max(first, _utc_day(float(newest) - DAY - self.ALLOWANCE) + timedelta(days=1))  # held already
        if last < first:
            return {"rows": [], "reached": True, "exhausted": False}
        start = max(first, last - timedelta(days=self.PAGE_DAYS - 1))
        title = ATTENTION[key][0]
        rows = []
        for item in fetcher.pageviews(title, start, last):
            day = date.fromisoformat(item["date"])
            if start <= day <= last:
                rows.append((self.stamp_of(day), {"article": title, "date": item["date"], "views": item["views"]}))
        reached = start <= first
        return {"rows": rows, "reached": reached, "exhausted": not rows and not reached}

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        """Each day with the mean of the seven days before it (None unless the history reaches back over all seven)."""
        views: dict[str, float] = {}
        out = []
        for at, payload in rows:
            day = str(payload.get("date") or "")
            prior = [views.get((date.fromisoformat(day) - timedelta(days=n)).isoformat()) for n in range(1, 8)] if day else []
            reach = since is not None and since <= at - 7 * DAY
            average = round(sum(prior) / 7.0, 2) if reach and prior and all(v is not None for v in prior) else None
            count = _num(payload.get("views"))
            ratio = round(count / average, 4) if average and count is not None else None
            out.append((at, {**payload, "avg_7d": average, "ratio_7d": ratio}))
            if day and count is not None:
                views[day] = count
        return out

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"pageviews", "pageview", "wikipedia", "wikimedia"}) or ({"page", "views"} <= words)


# ------------------------------------------------------------------------------------ GDELT
class NewsVolume(Source):
    """GDELT's count of news articles matching each subject, in 15-minute buckets over the last day, with
    the count of every article GDELT monitored in each (so a strategy can read a share, not a raw count).
    Source: the GDELT Project (gdeltproject.org), cited as its terms require.

    Terms (read Sept 25, 2026): https://www.gdeltproject.org/about.html -- GDELT's data is "available for
    unlimited and unrestricted use for any academic, commercial, or governmental use of any kind without
    fee", and any use must cite the GDELT Project with a link. No robots.txt on api.gdeltproject.org. The
    DOC 2.0 API is key-free; it answered the House's User-Agent in 14 s, and refused a second request 20 s
    later with HTTP 429 "Please limit requests to one every 5 seconds" (probed Sept 25, 2026). So each
    subject is its own poll, every three hours, and a poll waits until six seconds have passed since the
    last GDELT request; after a 429 every subject waits five minutes before GDELT is asked again.

    Receive-stamped and never backfilled: GDELT's counts for a recent bucket grow as it indexes articles."""

    name = "gdelt"
    host = "api.gdeltproject.org"
    source = ("gdelt (the GDELT Project, gdeltproject.org): api.gdeltproject.org/api/v2/doc/doc?query=<q>&mode=timelinevolraw&"
              "format=json&timespan=1d (15-minute article counts)")
    cadence = "every three hours a subject, at most one GDELT request every six seconds"
    what = ("per subject (bitcoin, ethereum, anthropic, openai, trump, fed, inflation, recession), GDELT's news coverage over the last "
            "day: {query, articles_24h, all_articles_24h, share_24h, points: [{t (the 15-minute bucket's start), articles, "
            "all_articles, share}] oldest first} -- data from the GDELT Project (gdeltproject.org)")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: GDELT's "
                     "counts for a recent bucket grow as it indexes more articles, so nothing is backfilled")
    every = 3 * 3600.0
    gap = 3 * 3 * 3600.0
    max_keys = 8
    timeout = 30.0
    warn_after = 3
    example = "bitcoin"
    note = "A bucket with no matching article is absent from points; share is articles over all_articles (None when zero)."
    SPACING = 6.0
    REFUSED_WAIT = 300.0

    def keys(self, recorder: Any) -> list[str]:
        return list(GDELT_QUERIES)

    def key_of(self, raw: Any) -> str | None:
        return attention_key(raw, tuple(GDELT_QUERIES))

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.signals import Signals

        return Signals(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        from ltcm.data import DataError

        state = recorder.state(self.name)
        out: dict[str, Any] = {}
        for key in keys:
            clock = float(recorder.clock())
            if clock < float(state.get("refused_until") or 0.0):
                out[key] = DataError(f"gdelt refused the House with HTTP 429; not asked again until "
                                     f"{datetime.fromtimestamp(state['refused_until'], timezone.utc):%H:%M:%SZ}")
                continue
            wait = self.SPACING - (clock - float(state.get("asked_at") or float("-inf")))
            if wait > 0:
                recorder._sleep(wait)
            state["asked_at"] = float(recorder.clock())
            try:
                points = fetcher.timeline(GDELT_QUERIES[key], "1d")
            except Exception as exc:  # noqa: BLE001 - a subject that fails is a failed poll of it
                if "HTTP 429" in str(exc):
                    state["refused_until"] = float(recorder.clock()) + self.REFUSED_WAIT
                out[key] = exc
                continue
            articles = sum(p["articles"] for p in points)
            every = sum(p["all_articles"] or 0 for p in points)
            out[key] = {"query": GDELT_QUERIES[key], "articles_24h": articles, "all_articles_24h": every,
                        "share_24h": round(articles / every, 8) if every else None, "points": points}
        return out

    def asks(self, words: set[str]) -> bool:
        return "gdelt" in words or ("news" in words and bool(words & {"volume", "volumes", "tone", "coverage", "count", "counts",
                                                                      "mentions", "intensity"}))


# ---------------------------------------------------------------------------------- hazards
_BASIN_KEYS = {"all": "all", "active": "all", "storms": "all", "hurricane": "all", "hurricanes": "all", "tropical": "all",
               "atlantic": "atlantic", "at": "atlantic", "al": "atlantic", "east_pacific": "east_pacific", "eastern_pacific": "east_pacific",
               "ep": "east_pacific", "central_pacific": "central_pacific", "cp": "central_pacific"}


class ActiveStorms(Source):
    """The National Hurricane Center's active tropical cyclones, as its storm list shows them now: for
    Kalshi's hurricane markets and the weather desks around them.

    Terms (read Sept 25, 2026): NWS and NHC information is "in the public domain ... may be used without
    charge for any lawful purpose" (https://www.weather.gov/disclaimer); the NHC asks programs to know
    its refresh frequency and keep retries a minute or more apart. robots.txt allows everything. The
    House's User-Agent was answered with JSON. One request every 30 minutes answers every basin."""

    name = "storms"
    host = "www.nhc.noaa.gov"
    source = "nhc: www.nhc.noaa.gov/CurrentStorms.json (the active tropical cyclones and their latest advisories)"
    cadence = "every 30 minutes"
    what = ("per basin (atlantic, east_pacific, central_pacific, all), the active tropical cyclones: {basin, count, storms: [{id, "
            "name, basin, bin, classification (TD, TS, HU, ...), intensity_kt, pressure_mb, lat, lon, movement_dir, movement_mph, "
            "last_update, advisory, advisory_issued, watches_warnings}]} -- count 0 and storms [] when none is active")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay; the list "
                     "is the NHC's current one, so nothing is backfilled (each storm carries its own advisory time)")
    batch = True
    every = 1800.0
    gap = 3 * 1800.0
    timeout = 20.0
    example = "atlantic"
    note = "An empty basin is a row with count 0: known to be quiet, not unavailable."
    BASINS = ("atlantic", "east_pacific", "central_pacific", "all")

    def keys(self, recorder: Any) -> list[str]:
        return list(self.BASINS)

    def key_of(self, raw: Any) -> str | None:
        return _BASIN_KEYS.get(_normal(raw))

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.hazards import Hazards

        return Hazards(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        storms = fetcher.storms()
        out = {}
        for key in keys:
            chosen = [s for s in storms if key == "all" or s["basin"] == key]
            out[key] = {"basin": key, "count": len(chosen), "storms": chosen}
        return out

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"hurricane", "hurricanes", "tropical", "cyclone", "cyclones", "nhc"}) or (
            bool(words & {"storm", "storms"}) and bool(words & {"active", "track", "tracks", "advisory", "advisories", "named"}))


_QUAKE_KEYS = {"m4.5_day": "4.5_day", "significant_week": "significant_week"}


class Earthquakes(Source):
    """The USGS earthquake feeds: every magnitude 4.5+ event of the past day and the week's significant
    ones, as the USGS lists them now (its events are revised as they are reviewed).

    Terms (read Sept 25, 2026): the GeoJSON feeds are "intended to be used as a programatic interface for
    applications" (https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php) and USGS-authored data
    is U.S. public domain (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits).
    No robots.txt. The House's User-Agent was answered with GeoJSON. One request a key every 15 minutes."""

    name = "quakes"
    host = "earthquake.usgs.gov"
    source = ("usgs: earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson and significant_week.geojson (updated every "
              "minute)")
    cadence = "every 15 minutes a feed"
    what = ("per feed (m4.5_day: magnitude 4.5 and above, past day; significant_week: the USGS's significant events, past week), "
            "{title, count, events: [{id, mag, mag_type, place, origin, updated, status (automatic or reviewed), tsunami, sig, alert, "
            "felt, lat, lon, depth_km}] newest origin first (at most 40)}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: the feed "
                     "is the USGS's current list and its events are revised, so nothing is backfilled (each event carries its "
                     "origin and last update)")
    every = 900.0
    gap = 3 * 900.0
    timeout = 20.0
    example = "m4.5_day"
    note = "A row changes when an event is added or revised; count 0 is a quiet feed, not an unavailable one."
    MAX_EVENTS = 40

    def keys(self, recorder: Any) -> list[str]:
        return list(_QUAKE_KEYS)

    def key_of(self, raw: Any) -> str | None:
        text = _normal(raw)
        aliases = {"m4.5_day": "m4.5_day", "4.5_day": "m4.5_day", "m45_day": "m4.5_day", "earthquakes": "m4.5_day", "quakes": "m4.5_day",
                   "significant_week": "significant_week", "significant": "significant_week"}
        return aliases.get(text)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.hazards import Hazards

        return Hazards(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        out: dict[str, Any] = {}
        for key in keys:
            try:
                feed = fetcher.quakes(_QUAKE_KEYS[key])
            except Exception as exc:  # noqa: BLE001 - a feed that fails is a failed poll of it
                out[key] = exc
                continue
            # `generated` moves every minute: left out, or every poll would read as new content.
            out[key] = {"title": feed["title"], "count": feed["count"], "events": feed["events"][:self.MAX_EVENTS]}
        return out

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"earthquake", "earthquakes", "quake", "quakes", "seismic", "usgs"})


# ------------------------------------------------------------------------------ crypto network
class Mempool(Source):
    """Bitcoin's network as mempool.space shows it: the fee rates that confirm in the next block, half
    hour and hour, the mempool's size, the coming difficulty adjustment and the hashrate.

    Terms (read Sept 25, 2026): mempool.space's terms (the source of its terms page in the mempool/mempool
    repository, updated Jul 10, 2024; the live page renders it with JavaScript) set no restriction on
    automated or commercial use of the public API; it rate-limits with HTTP 429 and may ban an address that
    ignores it. No robots.txt rule covers /api/. The House's User-Agent was answered with JSON. A pass asks
    three requests (fees, mempool, difficulty); the hashrate is asked once every six hours."""

    name = "mempool"
    host = "mempool.space"
    source = ("mempool.space: /api/v1/fees/recommended, /api/mempool, /api/v1/difficulty-adjustment and /api/v1/mining/hashrate/3d "
              "(every six hours)")
    cadence = "every 15 minutes (the hashrate every six hours)"
    what = ("BTC: bitcoin's network now: {fees: {fastest, half_hour, hour, economy, minimum} (sat/vB), mempool: {count, vsize, "
            "total_fee_sats}, difficulty: {progress_pct, change_pct (the estimate for the coming adjustment), previous_change_pct, "
            "remaining_blocks, retarget_height, estimated_retarget, block_seconds}, hashrate: {hashrate_ehs, difficulty, asked (when "
            "the House last asked for it)}}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay; the "
                     "hashrate part is the one received at its `asked` time (at or before the row's); nothing is backfilled")
    batch = True
    every = 900.0
    gap = 3 * 900.0
    timeout = 20.0
    example = "BTC"
    note = "Fee rates are sat/vB; a 429 from mempool.space is a failed poll, asked again at the next pass."
    HASHRATE_SECONDS = 6 * 3600.0

    def keys(self, recorder: Any) -> list[str]:
        return ["BTC"]

    def key_of(self, raw: Any) -> str | None:
        return "BTC" if _normal(raw) in ("btc", "bitcoin", "xbt", "mempool", "kxbtcd", "kxbtc") else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.chain import Chain

        return Chain(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        if "BTC" not in keys:
            return {}
        state = recorder.state(self.name)
        row = {"fees": fetcher.fees(), "mempool": fetcher.mempool(), "difficulty": fetcher.difficulty()}
        held = state.get("hashrate")
        if held is None or now - float(held["asked_at"]) >= self.HASHRATE_SECONDS:
            held = {**fetcher.hashrate(), "asked_at": float(now)}
            state["hashrate"] = held
        row["hashrate"] = {"hashrate_ehs": held["hashrate_ehs"], "difficulty": held["difficulty"],
                           "asked": datetime.fromtimestamp(held["asked_at"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        return {"BTC": row}

    def asks(self, words: set[str]) -> bool:
        return "mempool" in words or (bool(words & {"hashrate", "difficulty"}) and bool(words & {"bitcoin", "btc", "mining", "network"})) \
            or (bool(words & {"fee", "fees"}) and bool(words & {"onchain", "transaction", "transactions", "sat", "sats", "mempool"}))


class FearGreed(Source):
    """alternative.me's Crypto Fear & Greed Index: one value (0 extreme fear - 100 extreme greed) a UTC
    day, from volatility, momentum and volume, social media, dominance and search trends.

    Terms (read Sept 25, 2026): https://alternative.me/crypto/api/ -- "You are free to use our API ... this
    includes commercial projects of any kind"; attribution is required next to any display of the data
    (nothing here displays it); 60 requests a minute over ten minutes. No robots.txt rule covers the API.
    The House's User-Agent was answered with JSON.

    The stamp: each value carries its day's start (00:00 UTC) and the newest carries time_until_update,
    which on Sept 25, 2026 at 06:59Z counted down to 00:00Z on the 26th: a day's value is published at the
    day's start. How many minutes after 00:00 it appears was not measured, so a row is stamped two hours
    after its timestamp, live and in the backfill alike."""

    name = "fear_greed"
    host = "api.alternative.me"
    source = "alternative.me: api.alternative.me/fng/?limit=<days>&format=json (the Crypto Fear & Greed Index, daily)"
    cadence = "every six hours, five past 02, 08, 14 and 20 UTC; backfilled over the replay window"
    what = ("crypto: the Crypto Fear & Greed Index, one row a UTC day: {date, value (0 extreme fear - 100 extreme greed), "
            "classification, change_1d (against the day before), avg_7d (the mean of the seven days up to and including it)}")
    point_in_time = ("each row is a day's index stamped two hours after the day's start (the value is published at 00:00 UTC, by the "
                     "source's own countdown; the two hours are an allowance) and shown only from then on, live and in replay; the "
                     "history is backfilled from alternative.me's own record and stamped the same way, and change_1d and avg_7d read "
                     "only days at or before it")
    history = True
    every = 6 * 3600.0
    offset = 7500.0
    gap = 25 * 3600.0
    lookback_days = 7
    max_keys = 1
    timeout = 20.0
    example = "crypto"
    note = "change_1d and avg_7d are None until the days they read are held."
    ALLOWANCE = 2 * 3600.0
    MAX_DAYS = 400

    def keys(self, recorder: Any) -> list[str]:
        return ["crypto"]

    def key_of(self, raw: Any) -> str | None:
        return "crypto" if _normal(raw) in ("crypto", "fear_greed", "fng", "fear_and_greed", "btc", "bitcoin") else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.chain import Chain

        return Chain(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return "https://api.alternative.me/fng/?limit=<days>&format=json"

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        top = float(now) if before is None else min(float(now), float(before) - 0.001)
        days = min(self.MAX_DAYS, max(2, int(math.ceil((float(now) - float(floor)) / DAY)) + 2))
        answer = fetcher.fear_greed(days)
        rows = [(item["t"] + self.ALLOWANCE, {"date": item["date"], "value": item["value"], "classification": item["classification"]})
                for item in answer]
        oldest = min((at for at, _ in rows), default=None)
        reached = oldest is not None and oldest <= floor
        kept = [(at, payload) for at, payload in rows if floor <= at <= top]
        return {"rows": kept, "reached": reached, "exhausted": len(answer) < days and not reached}

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        values: dict[str, float] = {}
        out = []
        for at, payload in rows:
            day = str(payload.get("date") or "")
            value = _num(payload.get("value"))
            before = values.get((date.fromisoformat(day) - timedelta(days=1)).isoformat()) if day else None
            window = [value] + [values.get((date.fromisoformat(day) - timedelta(days=n)).isoformat()) for n in range(1, 7)] if day else []
            reach = since is not None and since <= at - 6 * DAY
            average = round(sum(window) / 7.0, 2) if reach and window and all(v is not None for v in window) else None
            out.append((at, {**payload, "change_1d": value - before if value is not None and before is not None else None,
                             "avg_7d": average}))
            if day and value is not None:
                values[day] = value
        return out

    def asks(self, words: set[str]) -> bool:
        return {"fear", "greed"} <= words or ("sentiment" in words and bool(words & {"crypto", "bitcoin", "btc"}))


# ====================================================================================================
# The government releases and notices.
# ====================================================================================================
_NEW_YORK = ZoneInfo("America/New_York")


def _et_day(moment: float) -> str:
    return datetime.fromtimestamp(float(moment), _NEW_YORK).date().isoformat()


def _count_today(rows: Sequence[tuple[float, Mapping[str, Any]]], field: str, weight: Callable[[Mapping[str, Any]], int]):
    """Each row with `field`: how many items the rows of its New York day at or before it hold (itself included)."""
    out, day, total = [], None, 0
    for at, payload in rows:
        today = _et_day(at)
        total = total + weight(payload) if today == day else weight(payload)
        day = today
        out.append((at, {**payload, field: total}))
    return out


# ---------------------------------------------------------------------- the White House's actions
class PresidentialActions(Source):
    """Each presidential action the White House posts -- executive orders, proclamations, memoranda,
    nominations -- stamped at the post's own publication time: what Kalshi's KXTRUMPACT ("Will Trump do
    anything today?") settles on (its settlement source is https://www.whitehouse.gov/presidential-actions/).

    Terms (read Sept 25, 2026): https://www.whitehouse.gov/copyright/ -- "government-produced materials
    appearing on this site are not copyright protected"; the site has no terms of use (/terms-of-use/ is a
    404) and robots.txt allows everything. The WordPress feed answered the House's contact User-Agent with
    RSS, no bot wall. A pass reads the feed's first page (thirty actions, about 0.6 MB) once for every key;
    the backfill reads `?paged=2`, `?paged=3` ... (a page is about a month of actions).

    The stamp is the feed's pubDate, the post's publication time to the second (UTC): the site's own record
    of when the action appeared. A post the White House backdated would carry the earlier time; nothing in
    the feed tells the two apart, and the history is stamped by the same rule live and backfilled."""

    name = "presidential"
    host = "www.whitehouse.gov"
    source = ("whitehouse: www.whitehouse.gov/presidential-actions/feed/ (RSS; ?paged=N for older pages): every presidential action "
              "the White House posts")
    cadence = "every 15 minutes; backfilled over the replay window"
    what = ("per key (actions: every presidential action; executive_orders, proclamations, memoranda, nominations: one kind), a row "
            "per posting moment: {published, count, actions: [{title, link, guid, kind, categories}] (the actions posted in that "
            "second), today_et (how many actions of the key the White House had posted that New York day, these included)}")
    point_in_time = ("each row is the actions posted in one second, stamped at the posts' own publication time (the feed's pubDate), "
                     "and shown only from then "
                     "on, live and in replay; the history is backfilled from the feed's older pages and stamped the same way; a "
                     "backdated post would carry its earlier time -- the feed cannot tell")
    history = True
    sparse = True
    every = 900.0
    offset = 120.0
    gap = 3600.0
    lookback_days = 1
    max_keys = 5
    timeout = 30.0
    example = "actions"
    note = ("today_et counts the key's actions of the row's New York day up to and including it; a day with no row had no action. "
            "KXTRUMPACT settles on this page.")
    KEYS = ("actions", "executive_orders", "proclamations", "memoranda", "nominations")
    ALIASES = {"kxtrumpact": "actions", "all": "actions", "presidential_actions": "actions", "eo": "executive_orders",
               "eos": "executive_orders", "executive_order": "executive_orders", "orders": "executive_orders",
               "proclamation": "proclamations", "memorandum": "memoranda", "memos": "memoranda", "memo": "memoranda",
               "nomination": "nominations", "appointments": "nominations"}
    MAX_PAGES = 6

    def keys(self, recorder: Any) -> list[str]:
        return list(self.KEYS)

    def key_of(self, raw: Any) -> str | None:
        text = "_".join(str(raw or "").strip().lower().replace("-", " ").split())
        text = self.ALIASES.get(text, text)
        return text if text in self.KEYS else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.notices import Notices

        return Notices(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return "https://www.whitehouse.gov/presidential-actions/feed/?paged=<n>"

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        top = float(now) if before is None else min(float(now), float(before) - 0.001)
        found: dict[float, list[dict[str, Any]]] = {}  # actions posted in the same second are one row (Sept 2026: three at once)
        reached = exhausted = False
        for number in range(1, self.MAX_PAGES + 1):
            items = _cached(recorder, self.name, f"page:{number}", now, 600.0, lambda n=number: fetcher.actions(n))
            if not items:
                exhausted = True
                break
            for item in items:
                if (key == "actions" or item["kind"] == key) and floor <= item["published_at"] <= top:
                    found.setdefault(item["published_at"], []).append({k: v for k, v in item.items() if k not in ("published_at", "published")})
            if min(item["published_at"] for item in items) <= floor:
                reached = True
                break
            if before is not None and min(item["published_at"] for item in items) < top and found:
                break  # a page back: this page brought the actions just older than the ones held
        rows = [(at, {"published": datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "count": len(posted),
                      "actions": posted}) for at, posted in sorted(found.items())]
        return {"rows": rows, "reached": reached, "exhausted": exhausted and not reached}

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        return _count_today(rows, "today_et", lambda payload: int(payload.get("count") or 0))

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"whitehouse", "kxtrumpact"}) or {"white", "house"} <= words or (
            "presidential" in words and bool(words & {"action", "actions", "orders", "order", "proclamations", "memoranda"})) or (
            "executive" in words and bool(words & {"order", "orders"}))


# ------------------------------------------------------------------------- the Federal Register
class FederalRegisterDocuments(Source):
    """The Federal Register's presidential documents -- executive orders, proclamations, memoranda -- a row
    per day's issue, stamped at the morning the issue is public.

    Terms (read Sept 25, 2026): the Federal Register's API needs no key ("No API keys are needed; all you
    need is an HTTP client or browser", its REST API developer page, read through the Aug 27, 2025 Wayback
    copy of https://www.federalregister.gov/reader-aids/developer-resources/rest-api because the live page
    answers automated clients with a CAPTCHA) and its block page says "programmatic access to these sites
    is limited to access to our extensive developer APIs": the House reads /api/v1/ only, never an HTML
    page; robots.txt allows /api/v1/. Federal Register documents are federal works, not copyrighted.

    The stamp: a document's publication_date is the day of the issue it appears in, and the API gives no
    time. The day's issue is on FederalRegister.gov by 6:00 a.m. Eastern (unverified); a day's row is
    stamped 09:00 New York time on its date, three hours later: late, never early. (A document was on
    public inspection the business day before; the inspection file's timestamp is kept, not trusted.)"""

    name = "federal_register"
    host = "www.federalregister.gov"
    source = ("federal register: www.federalregister.gov/api/v1/documents.json?conditions[type][]=PRESDOCU (the API only; the "
              "presidential documents of each day's issue)")
    cadence = "every four hours; backfilled over the replay window"
    what = ("per key (documents: every presidential document; executive_orders, proclamations, memoranda), one row per day's issue "
            "that has any: {date (the publication date), count, documents: [{document_number, title, subtype, signing_date, "
            "executive_order_number, proclamation_number, citation, html_url, public_inspection_url}]}")
    point_in_time = ("each row is a day's issue stamped 09:00 New York time on its publication date (the issue is online by 6:00 a.m. "
                     "Eastern; the API gives no time) and shown only from then on, live and in replay; the history is backfilled "
                     "from the API and stamped by the same rule")
    history = True
    sparse = True
    every = 4 * 3600.0
    offset = 900.0
    gap = 6 * 3600.0
    max_keys = 4
    timeout = 30.0
    example = "executive_orders"
    note = "A day with no row published no document of the key. signing_date is when the President signed it (usually days earlier)."
    KEYS = ("documents", "executive_orders", "proclamations", "memoranda")
    ALIASES = {"all": "documents", "presidential_documents": "documents", "eo": "executive_orders", "eos": "executive_orders",
               "executive_order": "executive_orders", "proclamation": "proclamations", "memorandum": "memoranda", "memos": "memoranda"}
    STAMP_HOUR = 9

    def keys(self, recorder: Any) -> list[str]:
        return list(self.KEYS)

    def key_of(self, raw: Any) -> str | None:
        text = "_".join(str(raw or "").strip().lower().replace("-", " ").split())
        text = self.ALIASES.get(text, text)
        return text if text in self.KEYS else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.notices import Notices

        return Notices(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return "https://www.federalregister.gov/api/v1/documents.json?conditions[type][]=PRESDOCU&conditions[publication_date][gte]=<day>"

    def stamp_of(self, day: date) -> float:
        return datetime(day.year, day.month, day.day, self.STAMP_HOUR, tzinfo=_NEW_YORK).timestamp()

    def _day_at(self, moment: float) -> date:
        """The newest publication day whose row is stamped at or before `moment`."""
        local = datetime.fromtimestamp(float(moment), _NEW_YORK)
        day = local.date()
        return day if self.stamp_of(day) <= float(moment) else day - timedelta(days=1)

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        from ltcm.data.notices import DOCUMENT_SUBTYPES

        top = float(now) if before is None else min(float(now), float(before) - 0.001)
        last = self._day_at(top)
        first = self._day_at(float(floor) - 0.001) + timedelta(days=1)  # the first day stamped at or after floor
        if last < first:
            return {"rows": [], "reached": True, "exhausted": False}
        # One request reads the whole span still missing (a sparse history is searched to its floor in one page:
        # a day without a document is only "none" once the listing was read over it); keys that ask the same
        # span in a pass share it.
        start = first
        memo = recorder.state(self.name).setdefault("memo", {})
        covering = [value for slot, (at, value) in list(memo.items()) if slot.startswith("docs:") and now - at < 600.0
                    and not isinstance(value, BaseException) and slot.split(":")[1] <= start.isoformat() <= last.isoformat()
                    <= slot.split(":")[2]]  # a read this pass already spanned these days (the live read, then the backfill)
        documents = [d for d in covering[0] if start.isoformat() <= d["publication_date"] <= last.isoformat()] if covering else \
            _cached(recorder, self.name, f"docs:{start}:{last}", now, 600.0, lambda: fetcher.documents(start.isoformat(), last.isoformat()))
        subtype = DOCUMENT_SUBTYPES.get(key)
        by_day: dict[str, list[dict[str, Any]]] = {}
        for document in documents:
            if subtype is None or document.get("subtype") == subtype:
                by_day.setdefault(document["publication_date"], []).append({k: v for k, v in document.items() if k != "publication_date"})
        rows = []
        for day, found in sorted(by_day.items()):
            at = self.stamp_of(date.fromisoformat(day))
            if floor <= at <= top:
                rows.append((at, {"date": day, "count": len(found), "documents": sorted(found, key=lambda d: d["document_number"])}))
        return {"rows": rows, "reached": True, "exhausted": False}

    def asks(self, words: set[str]) -> bool:
        return "federalregister" in words or {"federal", "register"} <= words


# ---------------------------------------------------------------------------------- EIA's tables
class FuelPrices(Source):
    """EIA's weekly U.S. retail gasoline and diesel prices and its daily WTI and Brent spot prices, from its
    public history tables -- no key, where the `eia` feed (api.eia.gov) waits for the owner's. Source: U.S.
    Energy Information Administration. Kalshi's gasoline series (KXAAAGAS*) settle on AAA's daily average,
    a different number from a different source, which is not recorded (no terms grant automated access).

    Terms (read Sept 25, 2026): https://www.eia.gov/about/copyrights_reuse.php -- EIA's data are public
    domain: "You may use and/or distribute any of our data", citing "Source: U.S. Energy Information
    Administration"; robots.txt does not disallow /dnav/. The House's contact User-Agent was answered
    with the tables (3-8 s each: EIA is slow). One request per series, every six hours."""

    name = "fuel"
    host = "www.eia.gov"
    source = ("eia (public tables, no key): www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=EMM_EPMR_PTE_NUS_DPG&f=W (gasoline), "
              "s=EMD_EPD2D_PTE_NUS_DPG (diesel), /dnav/pet/hist/RWTCD.htm (WTI), RBRTED.htm (Brent). Source: U.S. Energy Information "
              "Administration")
    cadence = "every six hours a series (gasoline and diesel are weekly, Mondays; WTI and Brent daily, released weekly)"
    what = ("per series (GASOLINE: U.S. regular retail, DIESEL: U.S. No 2 diesel retail, in dollars per gallon; WTI: Cushing spot, "
            "BRENT: Europe Brent spot, in dollars per barrel), EIA's newest published value: {series, what, unit, frequency, latest: "
            "{date, value}, recent: the ten newest [{date, value}], release_date, next_release}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: EIA "
                     "publishes a release date, never the moment a value appeared, so nothing is backfilled")
    every = 6 * 3600.0
    gap = 18 * 3600.0
    max_keys = 4
    timeout = 30.0  # EIA answered in 3-8 s
    example = "GASOLINE"
    note = "latest.date is the week's end (retail) or the trading day (spot); release_date is the day EIA published the table."
    ALIASES = {"GAS": "GASOLINE", "REGULAR": "GASOLINE", "RETAIL_GASOLINE": "GASOLINE", "EMM_EPMR_PTE_NUS_DPG": "GASOLINE",
               "EMD_EPD2D_PTE_NUS_DPG": "DIESEL", "KXDIESEL": "DIESEL", "KXDIESELW": "DIESEL", "KXDIESELD": "DIESEL",
               "CRUDE": "WTI", "RWTC": "WTI", "KXWTI": "WTI", "CL": "WTI", "RBRTE": "BRENT", "KXBRENT": "BRENT", "KXBRENTD": "BRENT"}

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.fuel import SERIES

        return list(SERIES)

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.fuel import SERIES

        text = "_".join(str(raw or "").strip().upper().replace("-", " ").split())
        text = self.ALIASES.get(text, text)
        return text if text in SERIES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.fuel import Fuel

        return Fuel(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        out: dict[str, Any] = {}
        for key in keys:
            try:
                out[key] = fetcher.series(key)
            except Exception as exc:  # noqa: BLE001 - a series that fails is a failed poll of it
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        # The `eia` feed's words too: it waits for the owner's key, and request_feed prefers the key-free feed
        # that records the same (review of #309). Not "gas" or "oil" alone: natural gas, AAA's average.
        fuel = "fuel" in words and bool(words & {"price", "prices", "retail", "weekly", "gasoline", "diesel"})
        return fuel or (bool(words & {"gasoline", "diesel", "wti", "brent", "crude", "petroleum"})
                        and bool(words & {"price", "prices", "retail", "weekly", "spot", "daily", "eia", "fixing", "fixings"}))


# ---------------------------------------------------------------------- the NWS's own CLI text
class ClimateReportText(Source):
    """The NWS Daily Climate Report of each settlement station as the NWS issued it: its raw text product,
    read the moment the NWS replaces it and parsed. The `cli` feed (league/open_feeds.py) records the same
    reports through the Iowa Environmental Mesonet's parse and backfills them; this one needs no third
    party and sees a report minutes after it is issued, but the NWS keeps only the newest, so it has no
    history before recording began.

    Terms (read Sept 25, 2026): https://www.weather.gov/disclaimer -- NWS information is public domain and
    "may be used without charge for any lawful purpose"; the NWS may block addresses that query too often
    (a station is asked every ten minutes, a failure not again within five). No robots.txt on
    tgftp.nws.noaa.gov; each file answered the House's User-Agent with the product (about 4 KB). New
    Orleans' file (cdus44.klix.cli.msy) answered a redirect to a directory and is left out."""

    name = "cli_text"
    host = "tgftp.nws.noaa.gov"
    source = "nws: tgftp.nws.noaa.gov/data/raw/cd/<wmo>.<office>.cli.<site>.txt (the newest CLI text product of each settlement station)"
    cadence = "every ten minutes a station, spread over passes; not backfilled (the NWS keeps only the newest report)"
    what = ("per settlement station, each Daily Climate Report as the NWS issued it, parsed: {office, wmo, product, issued, date (the "
            "climate day), final, preliminary, as_of, high, high_time, low, low_time (F, local standard time), precip_in, snow_in "
            "(0.0001 is a trace)}; preliminary is True for a same-day report ('VALID TODAY AS OF 0500 PM'), final once the report was "
            "issued after the climate day ended")
    point_in_time = ("each row is stamped with the product's own issue time (its WMO header's day and UTC time, in the month of its "
                     "issue line) and shown only from then on, live and in replay; the NWS keeps only the newest report, so nothing "
                     "before recording began exists -- the cli feed is the backfilled history of the same numbers")
    history = True
    every = 600.0
    offset = 60.0
    gap = 36 * 3600.0
    max_keys = 24
    timeout = 20.0
    pause = 0.5
    example = "KXHIGHNY"
    note = "Markets settle on the final report; the cli feed carries the same reports backfilled."

    def keys(self, recorder: Any) -> list[str]:
        from ltcm.data.cli_text import FILES

        return [station for station in _stations(recorder) if station in FILES]

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.cli_text import FILES

        key = _station_key(raw)
        return key if key in FILES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.cli_text import ClimateText

        return ClimateText(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        from ltcm.data.cli_text import FILES

        return f"https://tgftp.nws.noaa.gov/data/raw/cd/{FILES.get(key, '<file>')}.txt"

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: Any) -> dict[str, Any]:
        if before is not None:
            return {"rows": [], "reached": False, "exhausted": True}  # the NWS keeps only the newest report
        from ltcm.data.weather import city_of_station, standard_offset_hours

        report = fetcher.latest(key)
        at = float(report.pop("issued_at"))
        report["final"] = at >= _day_start(report["date"], standard_offset_hours(city_of_station(key))) + DAY
        rows = [(at, {"station": key, **report})] if floor <= at <= now else []
        return {"rows": rows, "reached": True, "exhausted": False}

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"cli", "climate"}) and bool(words & {"raw", "text", "product", "products", "tgftp"})


# ------------------------------------------------------------------------- release calendars
def _upcoming(rows: Sequence[Mapping[str, Any]], match: Callable[[str], bool], now: float, days: int) -> dict[str, Any]:
    from ltcm.data.calendars import upcoming

    ahead = [dict(row) for row in upcoming(list(rows), now, days) if match(str(row["release"]))]
    stamp_now = datetime.fromtimestamp(float(now), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    later = [row for row in ahead if row["at"] > stamp_now]
    return {"next": later[0] if later else None, "upcoming": ahead[:24]}


class _ReleaseCalendar(Source):
    """A statistical agency's release calendar, receive-stamped (shared by the BLS and BEA recorders)."""

    batch = True
    every = 12 * 3600.0
    gap = 36 * 3600.0
    timeout = 30.0
    DAYS = 60
    AGENCY = ""
    RELEASES: dict[str, tuple[str, ...]] = {}
    ALIASES: dict[str, str] = {}

    def keys(self, recorder: Any) -> list[str]:
        return list(self.RELEASES) + ["all"]

    def key_of(self, raw: Any) -> str | None:
        text = "_".join(str(raw or "").strip().lower().replace("-", " ").split())
        text = self.ALIASES.get(text, text)
        return text if text in self.RELEASES or text == "all" else None

    def _match(self, key: str) -> Callable[[str], bool]:
        if key == "all":
            return lambda title: True
        names = self.RELEASES[key]
        return lambda title: any(title.startswith(name) or name in title for name in names)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        rows = self.read(fetcher)
        return {key: {"agency": self.AGENCY, "release": key, **_upcoming(rows, self._match(key), now, self.DAYS)} for key in keys}


class BlsReleases(_ReleaseCalendar):
    """The Bureau of Labor Statistics' release calendar: when CPI, the Employment Situation, PPI, JOLTS and
    the rest come out (8:30 or 10:00 a.m. Eastern) -- what KXCPI, KXCPIYOY, KXCPICORE, KXU3 and KXPAYROLLS
    resolve on.

    Terms (read Sept 25, 2026): https://www.bls.gov/bls/linksite.htm -- "everything that we publish, both in
    hard copy and electronically, is in the public domain ... You are free to use our public domain material
    without specific permission" (cite BLS); robots.txt does not disallow /schedule/news_release/. The
    calendar file answered the House's contact User-Agent (text/calendar), no bot wall. One request twice a day."""

    name = "bls_releases"
    host = "www.bls.gov"
    AGENCY = "BLS"
    source = "bls: www.bls.gov/schedule/news_release/bls.ics (the economic news release calendar)"
    cadence = "twice a day"
    what = ("per release (cpi, jobs: the Employment Situation, ppi, jolts, eci, real_earnings, import_prices, productivity, all), "
            "BLS's schedule for the next 60 days: {agency, release, next: {release, at (UTC), date, time_et}, upcoming: [...]}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: BLS "
                     "publishes no time a calendar entry appeared or moved, so nothing is backfilled and a moved date is a new row")
    example = "cpi"
    note = "next is the soonest release still to come; upcoming includes today's, released or not."
    RELEASES = {"cpi": ("Consumer Price Index",), "jobs": ("Employment Situation",), "ppi": ("Producer Price Index",),
                "jolts": ("Job Openings and Labor Turnover Survey",), "eci": ("Employment Cost Index",),
                "real_earnings": ("Real Earnings",), "import_prices": ("U.S. Import and Export Price Indexes",),
                "productivity": ("Productivity and Costs",)}
    ALIASES = {"kxcpi": "cpi", "kxcpiyoy": "cpi", "kxcpicore": "cpi", "consumer_price_index": "cpi", "kxpayrolls": "jobs",
               "kxu3": "jobs", "payrolls": "jobs", "nfp": "jobs", "employment_situation": "jobs", "unemployment": "jobs",
               "producer_price_index": "ppi", "bls": "all"}

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.calendars import Calendars

        return Calendars(transport, timeout=self.timeout, clock=clock)

    def read(self, fetcher: Any) -> list[dict[str, Any]]:
        return fetcher.bls()

    def asks(self, words: set[str]) -> bool:
        timed = bool(words & {"calendar", "schedule", "schedules", "dates", "date", "times"})
        released = bool(words & {"release", "releases"})
        return timed and ("bls" in words or (released and bool(words & {"cpi", "jobs", "payrolls", "nfp", "ppi", "jolts", "economic"})))


class BeaReleases(_ReleaseCalendar):
    """The Bureau of Economic Analysis' release schedule: when GDP, Personal Income and Outlays (PCE) and the
    trade balance come out -- what KXGDP resolves on.

    Terms (read Sept 25, 2026): BEA is a federal agency whose works are not copyrighted (17 U.S.C. 105);
    https://www.bea.gov/help/guidelines-for-citing-bea asks only that it be cited, no BEA policy page
    (https://www.bea.gov/about/policies-and-information) restricts automated access, and robots.txt does not
    disallow /news/. The schedule page answered the House's contact User-Agent with HTML, no bot wall. BEA's
    data API needs a key (the owner's step); this reads only the public schedule page, twice a day."""

    name = "bea_releases"
    host = "www.bea.gov"
    AGENCY = "BEA"
    source = "bea: www.bea.gov/news/schedule (the release schedule table, an HTML page)"
    cadence = "twice a day"
    what = ("per release (gdp, pce: Personal Income and Outlays, trade, all), BEA's schedule for the next 60 days: {agency, release, "
            "next: {release, kind, at (UTC), date, time_et}, upcoming: [...]}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: BEA "
                     "publishes no time a schedule entry appeared or moved, so nothing is backfilled and a moved date is a new row")
    example = "gdp"
    note = "A page that changes shape is a failed poll, never a guessed date."
    RELEASES = {"gdp": ("GDP",), "pce": ("Personal Income and Outlays",), "trade": ("International Trade in Goods and Services",)}
    ALIASES = {"kxgdp": "gdp", "gross_domestic_product": "gdp", "personal_income": "pce", "kxpce": "pce", "bea": "all"}

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.calendars import Calendars

        return Calendars(transport, timeout=self.timeout, clock=clock)

    def read(self, fetcher: Any) -> list[dict[str, Any]]:
        return fetcher.bea()

    def asks(self, words: set[str]) -> bool:
        timed = bool(words & {"calendar", "schedule", "schedules", "dates", "date", "times"})
        return timed and ("bea" in words or ("gdp" in words and bool(words & {"release", "releases"})))


# ---------------------------------------------------------------------------------- trading halts
class TradeHalts(Source):
    """Nasdaq Trader's trade halts: every U.S. listed stock halted today (and the long-standing halts), with
    the reason code and, once it is known, the resumption -- for the equity desks' stocks and in all.

    Terms (read Sept 25, 2026): https://www.nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS -- "The Trade Halt
    RSS Feed is a free service", with its own terms
    (https://www.nasdaqtrader.com/content/administrationsupport/agreementstrading/THRSSFeedTermsCond.pdf),
    which bar only editing or misrepresenting the feed; "Please do not query the data more than once a
    minute" -- the House asks every five minutes, one request for every key. No robots.txt; answered the
    House's contact User-Agent with RSS.

    Receive-stamped, not at the halt time: a halt's item changes when the issue resumes (its resumption
    times fill in), and a history row keeps its first version, so each change is a new row at the moment
    the House saw it; the feed holds only the day's halts, so there is nothing to backfill."""

    name = "halts"
    host = "www.nasdaqtrader.com"
    source = "nasdaq: www.nasdaqtrader.com/rss.aspx?feed=tradehalts (the Trade Halt RSS feed)"
    cadence = "every five minutes"
    what = ("per stock the equity desks trade, and `all`: the halts the feed lists now: {symbol (None for all), count, halts: [{symbol, "
            "name, market, reason (Nasdaq's halt code: T1 news pending, LUDP volatility pause, H10 SEC suspension ...), halted (UTC), "
            "pause_threshold, resumed_quotes, resumed_trading}]} -- an empty list is a stock not halted")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: a halt's "
                     "resumption fills in after it began, so every change is a new row when the House saw it; the feed holds only the "
                     "current halts, so nothing is backfilled")
    batch = True
    every = 300.0
    gap = 3 * 300.0
    max_keys = 40
    timeout = 20.0
    example = "AAPL"
    note = "halted is the halt's own time (Eastern in the feed, UTC here); a stock with no halt has halts []."

    def keys(self, recorder: Any) -> list[str]:
        from .feeds import earnings_tickers

        return earnings_tickers(recorder.niches())[: self.max_keys - 1] + ["all"]

    def key_of(self, raw: Any) -> str | None:
        from .feeds import _ticker_key

        text = str(raw or "").strip()
        return "all" if text.lower() in ("all", "halts", "every") else _ticker_key(text)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.notices import Notices

        return Notices(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: Any, now: float) -> Mapping[str, Any]:
        halts = fetcher.halts()
        out: dict[str, Any] = {}
        for key in keys:
            found = halts if key == "all" else [row for row in halts if row["symbol"] == key]
            out[key] = {"symbol": None if key == "all" else key, "count": len(found), "halts": found}
        return out

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"halt", "halts", "halted", "luld", "suspension", "suspensions"}) and not words & {"circuit", "kalshi"}


# ------------------------------------------------------------------ the requests no recorder answers
@dataclass(frozen=True)
class Refusal:
    """A request no recorder here can answer, by the I2 rule it fails: each group of `needs` must share a
    word with the request's name. `owner` is "owner" when the owner can unlock it (a key, a login, a paid
    plan) and "no-source" when no source that passes the rule publishes it."""

    name: str
    needs: tuple[frozenset[str], ...]
    rule: str
    owner: str

    def matches(self, words: set[str]) -> bool:
        return all(words & group for group in self.needs)

    def outcome(self) -> str:
        return (f"Refused by rule (league/open_feeds.py, workstream I3 of docs/goals/LTCM_KALSHI_SCALE.md): {self.rule}. "
                "Nothing will be recorded for it unless that changes; the feeds that are recorded are listed in runtime_status "
                "(observations.feeds).")


_CRYPTO_WORDS = frozenset(("crypto", "btc", "eth", "bitcoin", "ethereum", "sol", "xrp", "coin", "coins", "spot", "hyperliquid", "kraken",
                           "coinbase", "external"))

REFUSALS: tuple[Refusal, ...] = (
    Refusal("polymarket", (frozenset(("polymarket", "polymarkets")),),
            "the site's terms forbid automated access by a trading firm: Polymarket's Terms of Use (effective Aug 11, 2026, "
            "polymarket.com/tos) bar 'data mining tools, robots, crawlers' and bar proprietary trading firms and hedge funds from its "
            "data, 'directly or through an API', without a written agreement", "no-source"),
    Refusal("player_props", (frozenset(("prop", "props")),),
            "needs a paid key: sportsbook player-prop odds and their history are sold by paid feeds (The Odds API's player-prop "
            "markets are on its paid plans), and no key-free source publishes them point in time -- the owner's step", "owner"),
    Refusal("odds_history", (frozenset(("odds", "sportsbook", "sportsbooks", "lines", "moneyline", "moneylines")),
                             frozenset(("history", "historical", "backfill", "archive", "archived", "closing"))),
            "needs a paid key: sportsbooks' historical lines are a paid product (The Odds API's historical endpoint); the odds feed "
            "records ESPN's lines live from when recording began -- the owner's step", "owner"),
    Refusal("lineups", (frozenset(("lineup", "lineups", "pitcher", "pitchers", "probable", "probables", "batting", "scratch",
                                   "scratches", "starters", "roster", "rosters")),),
            "the sources that publish it forbid automated access by a trading firm: MLB's statsapi (gdx.mlb.com/components/"
            "copyright.txt: 'only individual, non-commercial, non-bulk use'; mlb.com's terms ban automated scripts), the NHL's and "
            "NBA's APIs (their terms ban scraping and allow only personal, non-commercial use), and ESPN answers the House's "
            "identified User-Agent with 403", "no-source"),
    Refusal("injuries", (frozenset(("injury", "injuries", "inactive", "inactives")),),
            "the sources that publish injury reports key-free forbid commercial use: Sleeper's API is 'free to use for "
            "non-commercial purposes' (docs.sleeper.com), and the leagues' own sites ban automated access", "no-source"),
    Refusal("index_rebalances", (frozenset(("rebalance", "rebalances", "rebalancing", "reconstitution", "reweighting")),),
            "no key-free source publishes it point in time: index providers publish rebalance notices as licensed documents and "
            "press releases, with no key-free machine-readable feed stamped at publication", "no-source"),
    Refusal("crypto_index_history", (frozenset(("index", "indexes", "indices", "oracle", "oracles")),
                                     frozenset(("history", "historical", "backfill", "archive", "timestamps", "timestamped")),
                                     _CRYPTO_WORDS),
            "no key-free source publishes it point in time: Hyperliquid's public API answers only the current oracle price, and "
            "Kraken's public data -- its index candles included -- needs Kraken's prior permission for any non-personal commercial "
            "use (docs.kraken.com)", "no-source"),
    Refusal("exchange_terms", (frozenset(("coinbase", "kraken", "bitstamp", "binance", "gemini", "bitfinex", "defillama", "llama")),
                               frozenset(("candle", "candles", "ohlc", "ohlcv", "orderbook", "book", "trades", "spot", "tvl", "bars",
                                          "ticker", "tickers", "depth"))),
            "the site's terms forbid it for a trading firm: Coinbase's market data terms allow only personal or research use and bar "
            "valuing derivatives with it (coinbase.com/legal/market_data), Kraken and Bitstamp require a commercial data licence, "
            "Binance.US's robots.txt disallows everything, Gemini bars using its data to price a financial contract, and "
            "DefiLlama's terms are non-commercial and ban automated means; OKX, Deribit, Hyperliquid and Kraken Futures are "
            "recorded (perps, vol, funding, oi)", "no-source"),
    Refusal("fred", (frozenset(("fred", "stlouisfed", "alfred")),),
            "needs a key: FRED licenses its downloads for personal, non-commercial use and program access goes through its API key "
            "(fred.stlouisfed.org/legal) -- the owner's step (a free FRED API key)", "owner"),
    Refusal("cboe", (frozenset(("cboe", "vix", "vix9d", "vix3m", "vvix", "skew")),),
            "the site's terms forbid automated access: Cboe's delayed data is for 'personal non-commercial use' and it bans "
            "downloading it with auto-extraction programs (cboe.com/terms); a licensed data feed is the owner's step", "owner"),
    Refusal("aaa_gas", (frozenset(("aaa",)),),
            "no source that passes the rule publishes it: gasprices.aaa.com offers no API and no terms that grant automated access; "
            "EIA's weekly retail prices are the eia feed (the owner's key)", "no-source"),
    Refusal("census", (frozenset(("census",)),),
            "needs a key: api.census.gov now answers every request without a key with 'A valid key must be included' -- the "
            "owner's step (a free Census API key)", "owner"),
    Refusal("inflation_nowcast", (frozenset(("nowcast", "nowcasting", "cleveland", "clevelandfed")),
                                  frozenset(("inflation", "cpi", "pce", "cleveland", "clevelandfed"))),
            "the site's terms forbid it: the Cleveland Fed allows reuse only 'for noncommercial, personal, or educational purposes'",
            "no-source"),
    Refusal("predictit", (frozenset(("predictit",)),),
            "the site's terms forbid it: PredictIt licenses its API data 'for non-commercial use'", "no-source"),
    Refusal("openrouter", (frozenset(("openrouter", "kxtokenuse", "kxanthshare", "kxopenshare", "kxdeepshare", "kxgoogshare",
                                      "kxzaishare")),),
            "needs a key: OpenRouter's rankings (what KXTOKENUSE and the AI share markets settle on) are served key-free only "
            "inside its web page, and its terms bar scraping the site with 'scripts, robots ... or any other automated technology' "
            "(openrouter.ai/terms, section 7); its rankings dataset API needs an OpenRouter key -- the owner's step (a free key; the "
            "data is CC BY 4.0)", "owner"),
    Refusal("ai_share", (frozenset(("ai", "llm", "llms", "model", "models", "token", "tokens")),
                         frozenset(("share", "shares", "rankings", "ranking", "usage"))),
            "needs a key: the AI model usage and share rankings Kalshi's markets settle on are OpenRouter's, served to programs "
            "only through its keyed dataset API (openrouter.ai/terms bars scraping the site) -- the owner's step", "owner"),
    # Not "estimate": BEA names its releases so ("gdp_advance_estimate_values" is BEA's print, the owner's key).
    Refusal("econ_consensus", (frozenset(("consensus", "surprise", "surprises", "expectation", "expectations", "expected")),
                               frozenset(("cpi", "payrolls", "nfp", "gdp", "unemployment", "jobs", "inflation", "pce", "ppi", "claims",
                                          "jobless", "retail"))),
            "no key-free source publishes it: economists' consensus forecasts are sold by data vendors or shown on sites whose "
            "terms forbid automated use; the bls feed records the published values themselves", "no-source"),
    Refusal("bea_data", (frozenset(("bea", "gdp", "pce")),
                         frozenset(("data", "value", "values", "actual", "actuals", "series", "print", "prints", "history",
                                    "historical", "estimate", "advance"))),
            "needs a key: BEA's data API (GDP, PCE) needs a registration key (apps.bea.gov/API/signup) -- the owner's step",
            "owner"),
    Refusal("gdpnow", (frozenset(("gdpnow", "atlantafed", "atlanta")),),
            "the site's terms forbid it: the Atlanta Fed permits GDPNow's data 'for personal and educational use only', not for "
            "commercial gain (atlantafed.org/terms-of-use)", "no-source"),
    Refusal("truth_social_count", (frozenset(("truth", "truthsocial", "factbase", "kxtruthsocial")),
                                   frozenset(("post", "posts", "count", "counts", "truths", "number", "factbase", "kxtruthsocial"))),
            "no source that passes the rule publishes it: Truth Social offers no key-free API whose terms allow automated "
            "reading, and Roll Call's Factbase (what KXTRUTHSOCIAL settles on) publishes no terms that grant automated access "
            "and serves its listing only through an internal endpoint", "no-source"),
    Refusal("prediction_venues", (frozenset(("manifold", "metaculus", "smarkets", "betfair")),),
            "the sites' terms forbid it for a trading firm: Manifold licenses its content 'solely for your personal, "
            "non-commercial use' (docs.manifold.markets/terms), Metaculus's API now needs a token (the owner's step) and "
            "Betfair's and Smarkets' need an account", "no-source"),
    Refusal("crypto_aggregators", (frozenset(("coingecko", "gecko", "coinmarketcap", "cmc", "blockchaininfo", "coincap",
                                              "cryptocompare")),),
            "needs a paid plan or forbids it: CoinGecko's robots.txt disallows /api/v3 and its commercial licence is a paid plan, "
            "CoinMarketCap, CoinCap and CryptoCompare need keys, and Blockchain.com's API terms are personal and non-commercial; "
            "mempool.space (mempool) and alternative.me (fear_greed) are recorded", "owner"),
    Refusal("f1", (frozenset(("f1", "formula", "jolpica", "ergast")),),
            "the source's terms forbid it: Jolpica F1 (the Ergast successor) is 'freely available for non-commercial use' under "
            "CC BY-NC-SA", "no-source"),
    Refusal("league_stats", (frozenset(("statsapi", "statcast", "mlb", "nfl", "ncaaf", "nba", "nhl", "wnba", "ncaa", "ncaab", "boxscore", "boxscores")),
                             frozenset(("stats", "statistics", "statcast", "boxscore", "boxscores", "splits", "pbp", "play", "plays",
                                        "player", "players", "advanced"))),
            "the sources that publish it forbid automated access by a trading firm: the MLB, NHL, NBA and NCAA sites and APIs allow "
            "only personal, non-commercial use and ban scraping (the NBA's also bans use in connection with any gambling)",
            "no-source"),
)


def refusal_for(name: Any) -> Refusal | None:
    """The rule a tool request's name plainly fails (`REFUSALS`), or None."""
    from .feeds import _words

    words = _words(name)
    if not words:
        return None
    return next((rule for rule in REFUSALS if rule.matches(words)), None)


def refuse_requests(commons: Any, skip: Sequence[str] = ()) -> list[str]:
    """Answer, by rule, the OPEN tool requests no recorder can fulfil and a refusal rule names: a
    `tool.blocked` row with the rule (`commons.block`), owner "owner" for what the owner can unlock and
    "no-source" otherwise. Never a request a recorder answers (`feeds.request_feed`, shipped or not),
    and never one already blocked or fulfilled: a blocked request is no longer open, so this is
    idempotent -- and a recorder that later answers it still fulfils it (`fulfil_requests` reads the
    blocked ones too)."""
    from .feeds import request_feed

    done: list[str] = []
    for row in list(commons.open_requests(stale_days=0)):
        ident = str(row.get("id") or "")
        if not ident or ident in skip or ident in done or request_feed(row.get("name")) is not None:
            continue
        rule = refusal_for(row.get("name"))
        if rule is not None:
            commons.block(ident, rule.outcome(), owner=rule.owner, change="league/open_feeds.py")
            done.append(ident)
    return done


#: What league.feeds registers into RECORDERS, in the order a request's words are tried after the
#: recorders of Sept 24, 2026.
SOURCES: tuple[Source, ...] = (
    ClimateReports(), StationObservations(), DailySummaries(), KalshiCandles(),
    BlsSeries(), TreasuryFiscal(), EcbReferenceRates(), CommitmentsOfTraders(), FedCalendar(),
    Pageviews(), NewsVolume(), ActiveStorms(), Earthquakes(), Mempool(), FearGreed(),
    PresidentialActions(), FederalRegisterDocuments(), FuelPrices(), ClimateReportText(), BlsReleases(), BeaReleases(), TradeHalts(),
)

