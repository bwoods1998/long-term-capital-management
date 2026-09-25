"""The signals group of the Kalshi-scale run's recorders (Sept 25, 2026, workstream I2): attention
(Wikipedia pageviews, GDELT's news volume), hazards (the NHC's active storms, the USGS earthquake
feed) and crypto network and mood (mempool.space, alternative.me's Fear & Greed Index).

Built beside league/open_feeds.py (its docstring holds the rule every host here passed, and its
helpers); merged into it before the run's PR is final. Each Source's docstring names the terms it was
checked against and the URL read.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from .feeds import Source, _num
from .open_feeds import DAY

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


SOURCES: tuple[Source, ...] = (Pageviews(), NewsVolume(), ActiveStorms(), Earthquakes(), Mempool(), FearGreed())
