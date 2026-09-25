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
from datetime import datetime, timedelta, timezone  # noqa: E402
from functools import lru_cache  # noqa: E402
from typing import Any, Callable, Mapping, Sequence  # noqa: E402

from .feeds import NOT_LISTED, Source, stamp  # noqa: E402

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
    timeout = 45.0
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
    timeout = 60.0
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
    note = ("markets_read < markets_listed means the busiest markets (by lifetime volume) were read and the rest were not; an hour "
            "with no row is not recorded, an hour whose row has no markets had no activity in the markets read.")
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
        markets = [m for m in fetcher.markets(key, closing_from=opened, closing_to=last + self.CLOSE_AFTER_DAYS * DAY)
                   if m["open"] is not None and m["open"] < last and m["volume"] > 0]
        markets.sort(key=lambda m: -m["volume"])
        read = [m["ticker"] for m in markets[:self.MAX_MARKETS]]
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
                                    "markets_read": len(read), "markets_listed": len(markets), "markets": markets_now}))
            hour += HOUR
        return {"rows": rows_out, "reached": top_first <= first, "exhausted": False}

    def asks(self, words: set[str]) -> bool:
        kalshi = "kalshi" in words or any(w.startswith("kx") for w in words)
        return kalshi and bool(words & {"candle", "candles", "candlestick", "candlesticks", "volume", "volumes", "capacity", "prints",
                                        "trades", "traded", "liquidity", "hourly", "ohlc"}) \
            and not words & {"orderbook", "book", "depth", "fills", "fill", "outcome", "outcomes"}


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
                                  frozenset(("inflation", "cpi", "pce", "nowcast", "nowcasting"))),
            "the site's terms forbid it: the Cleveland Fed allows reuse only 'for noncommercial, personal, or educational purposes'",
            "no-source"),
    Refusal("predictit", (frozenset(("predictit",)),),
            "the site's terms forbid it: PredictIt licenses its API data 'for non-commercial use'", "no-source"),
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
SOURCES: tuple[Source, ...] = (ClimateReports(), StationObservations(), DailySummaries(), KalshiCandles())

# BUILD SCAFFOLD (removed before the PR is final): the groups built in parallel live in their own
# modules until they are merged into this one.
for _group in ("open_feeds_macro", "open_feeds_signals", "open_feeds_more"):
    try:
        _module = __import__(f"league.{_group}", fromlist=["SOURCES"])
    except ModuleNotFoundError as _missing:
        if _missing.name != f"league.{_group}":
            raise
        continue
    SOURCES = SOURCES + tuple(_module.SOURCES)
