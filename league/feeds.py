"""Feeds the House records for its strategies: ESPN scoreboards, perpetual funding and open interest,
and two point-in-time histories for the crypto desks -- Deribit's implied-vol index (DVOL) and OKX's
settled funding rates.

Measured on the production ledger, Sept 22, 2026: 43 agents had asked for live sports scores or
game state and 32 for crypto perpetual funding rates or open interest -- in tool requests, in
research summaries ("the perpetual funding/OI feed remains not_supplied") and in paid consults.
The fetchers had existed since the arena of Sept 18 (`ltcm/data/sports.py`, `ltcm/data/derivs.py`)
and the House box could reach their hosts, but nothing in `league/` called them: no strategy could
read either, live or in replay.

Measured Sept 22-23, 2026: every Alpaca crypto strategy failed replay on out-of-sample growth once
fees were paid (0.30-0.50% a round trip), almost nothing passed on the Kalshi crypto desks, and
overnight nothing on Alpaca traded. The swarm needs new information for 24/7 crypto and a replay
that can test it now, and the live feeds cannot give that: stamped when received and never
backfilled, a strategy that reads them waits twenty blocks of recording for its replay. Two
histories CAN be fetched honestly, because every value in them has a moment it became final and
the venue publishes it with that moment: a DVOL candle at its close, a funding rate at its
settlement. A Kalshi crypto strike (KXBTCD, KXBTC15M ...) is an option on spot: with spot bars
(`NEEDS["observe"]`) and implied vol a strategy can price it and bid only where its model clears the
ask and the fee; and funding extremes are the classic crowding signal of a market that never closes.

WHAT IS RECORDED

- `sports`: one ESPN scoreboard per league whose Kalshi series the sports desks trade
  (`SPORTS_SERIES`: a series no league maps is reported as unmapped, never guessed), every 60 s
  while a game of that league is live or starts within 90 minutes and every 15 minutes otherwise.
  A row is `{"league", "espn", "events"}`, each event as `ltcm.data.sports.event_row` makes it
  (status, score, clock, period, start, the sportsbook line). ESPN's scoreboard is the current
  board: the House never asks it for a past date, because a past date's board carries the final
  scores and would leak the future into a replay.
- `perps`: `Derivatives.snapshot` for the coins the crypto desks trade (`perp_coins`: the Alpaca
  crypto symbols and the coins of the Kalshi crypto series), every 5 minutes: OKX, Hyperliquid and
  Kraken funding and open interest, Deribit's DVOL for BTC and ETH, the OKX funding z-score. A
  coin no venue answered for is a failed poll, not a row of Nones.
- `vol`: Deribit's DVOL (its 30-day implied volatility index) for BTC and ETH (`VOL_KEYS`: no other
  coin has one), a row per COMPLETED hourly candle (`Derivatives.dvol_candles`) stamped at its
  close: `{"t": <close>, "open", "high", "low", "close", "hours": 1, "change_24h"}`, where
  `change_24h` is the close minus the close of the candle that closed 24 hours earlier (None when
  the store does not hold it). Polled 90 seconds after every hour; a candle still open is never
  stored.
- `funding`: OKX's settled funding (`Derivatives.okx_funding_settled`) for the coins `perps`
  records, a row per settlement stamped at its `fundingTime`: `{"t": <fundingTime>, "rate",
  "interval_hours", "avg_24h", "avg_7d", "zscore_30d"}` (`_funding_rows` says how each is made from
  the rates settled at or before it). Polled every 30 minutes, 90 seconds past the hour and the
  half hour; a rate not yet settled is never stored.

  Both are BACKFILLED. The recorder pages back through the venue's own history (Deribit's candles,
  OKX's funding-rate-history) until it holds `backfill_days` -- the longest live replay window a
  strategy reading them could be replayed over, plus a week, and at least `BACKFILL_DAYS` -- plus
  what each feed's derived fields read before it (`LOOKBACK_DAYS`), or until the venue has nothing
  older. That is `BACKFILL_PAGES` pages a pass at most, a second apart, and a pass gives way as soon
  as a live poll falls due: the feeds lane has one slot. The oldest row held is the cursor, so a
  House that restarts continues where the last pass stopped and never fetches a page twice; and
  `backfills` keeps, for each key, the endpoint its rows came from, the span they cover, and whether
  the backfill has reached its target (the provenance).

THREE RULES KEEP IT HONEST (as in `league/options_history.py`).

1. **Point in time.** A row is stamped `t` with the moment it became knowable, and it is visible at
   a moment only if `t` is at or before it -- live (`latest`) and in replay (`series`,
   `league/replay.py`) alike. For `sports` and `perps` that is when the House RECEIVED it (its
   clock once the fetch returned, rounded up to the millisecond). They are never backfilled, so a
   replay can use them only over the time they have been recorded: the House replays a strategy
   that declares them only once they span the replay gate's `min_blocks` blocks of its horizon,
   and refuses it as unsupported input (not a trial) until then. For `vol` and `funding` it is the
   moment the value became FINAL -- a candle's close, a rate's settlement -- and a backfilled row is
   stamped the same way, never with the time it was fetched; a derived field reads only rows
   stamped at or before its own. That history is point-in-time history, so it counts as covered: a
   strategy that declares these feeds is replayed as soon as the backfill spans its window.
2. **Nothing is fabricated.** A source that fails is a `polls` row with ok=0 and its error, and
   nothing is stored for it. A key the House does not record is absent from `ctx["feeds"]`: it is
   unavailable, never an empty or zero row. A candle still open and a rate not yet settled are
   never stored, and a derived field whose window the history does not reach is None.
3. **Unchanged content is stored once.** A poll whose content has the digest of the key's last
   snapshot adds a `polls` row and no snapshot: a quiet scoreboard costs almost nothing, and a
   row's `t` is when that content was FIRST received. A `vol` or `funding` row is its stamp: a
   candle or a settlement already held is never stored again and the first version received
   stands -- while two settlements at the same rate are two rows (OKX's rate often sits at its
   floor for days).

Standard library only (and `ltcm.data` for the fetchers). One sqlite connection per thread: the
store is written by the House's feeds lane and read by wake threads, the replay lane and research.
"""

from __future__ import annotations

import bisect
import gzip
import hashlib
import json
import math
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

DB_NAME = "feeds.sqlite"
FEEDS = ("sports", "perps", "vol", "funding")
#: The feeds whose rows are a venue's own settled history, stamped when each value became final and
#: backfilled over the replay window. The others are recorded live and never backfilled.
HISTORY_FEEDS = ("vol", "funding")
#: DVOL exists for BTC and ETH only (`ltcm/data/derivs.py`: other currencies answer no data).
VOL_KEYS = ("BTC", "ETH")
#: What one strategy may ask for, per feed (as `NEEDS["observe"]` allows six of each).
MAX_KEYS = 6
SPORTS_LIVE_SECONDS = 60
SPORTS_QUIET_SECONDS = 900
#: A board with a game starting this soon is polled as if the game were on.
SPORTS_SOON_SECONDS = 90 * 60
PERPS_SECONDS = 300
HOUR = 3600.0
VOL_SECONDS = 3600
FUNDING_SECONDS = 1800
#: How long after each hour (`vol`) and half hour (`funding`) they are polled: the candle that
#: closed on the hour, and a rate settled at 00:00, 08:00 or 16:00 UTC, are final and published by then.
HISTORY_OFFSET = 90
#: A source that failed is asked again this soon (a live board keeps its minute).
RETRY_SECONDS = 300
#: One warning per feed per hour at most, and never an error: an error alert inside a release's
#: watch rolls the release back, and a scoreboard that is down says nothing about the release.
ALERT_SECONDS = 3600
COVERAGE_SECONDS = 3600
#: How long one successful poll counts as coverage when the next is late (twice the quiet
#: cadence for a scoreboard, three polls for perps): a House that was down covers nothing. For
#: `vol` and `funding` coverage is measured on the ROWS -- the backfilled ones too -- and this is how
#: long one row counts when the next is missing: a candle two hours, a settlement nine (its eight
#: hours and one more).
GAP_SECONDS = {"sports": 2 * SPORTS_QUIET_SECONDS, "perps": 3 * PERPS_SECONDS, "vol": 2 * VOL_SECONDS, "funding": 9 * 3600}
#: How far back the backfill reaches at the least, in days (`FeedRecorder.backfill_days` takes the
#: House's own windows): the longest live replay window of a strategy that could read these feeds
#: is a Kalshi daily one's 49 days (`kalshi_replay_days` x 7), then an Alpaca hourly one's 21 and a
#: Kalshi hourly one's 7 (Sept 23, 2026). An Alpaca daily strategy's 126 days need only `min_blocks`
#: of them covered, and OKX answers about three months of funding (its docs; UNVERIFIED).
BACKFILL_DAYS = 60
BACKFILL_MARGIN_DAYS = 7
#: The history before a row that its derived fields read -- a day for `change_24h`, 30 days for
#: `zscore_30d` -- fetched as well, so the first row of the window has them too.
LOOKBACK_DAYS = {"vol": 1, "funding": 30}
#: One DVOL request asks for this many hourly candles (Deribit's docs page at 1000 points; a
#: continuation that comes back anyway is followed from the oldest candle received).
VOL_PAGE_HOURS = 720
#: OKX's funding-rate-history answers at most 100 settlements a request.
FUNDING_PAGE = 100
#: A backfill pass runs at most this often while history is missing, fetches at most this many
#: pages, a pause apart, and gives way after this many seconds or when a live poll falls due.
BACKFILL_SECONDS = 60
BACKFILL_PAGES = 10
BACKFILL_PAUSE = 1.0
BACKFILL_RUN_SECONDS = 30.0
#: Between the funding pass's requests: eighteen coins at the transport's 0.1 s would be ten a
#: second, and OKX's docs allow this endpoint ten per two seconds.
OKX_PAUSE = 0.35
#: A live poll after a long outage pages back to the newest row held, at most this many pages
#: (the backfill window is three DVOL pages and one OKX page): the history stays without holes.
HEAD_PAGES = 12
#: An instrument OKX does not list (`okx code 51001`) is asked again after this long, not every pass.
UNLISTED = "okx code 51001"
UNLISTED_SECONDS = 6 * 3600
#: The feed rows one replay tape may carry, as JSON. A tape is handed whole to a sealed box, and
#: seven-week sports tapes were killed for memory (exit 137) on Sept 19, 2026: a key over its share
#: is sampled at a coarser step instead.
TAPE_BYTES = 8 * 1024 * 1024
TIMEOUT = 10.0
#: The replay refusal that means "recorded, not yet long enough" (`House._replay_own` treats it as a
#: wait, not as a replay that could not run).
WAITING = "unsupported input: feeds recorded live since"
#: And "a backfilled feed with no history in yet" (the first pass has not run, or its venue is down):
#: a wait too, never a replay that could not run.
BACKFILLING = "unsupported input: feeds being backfilled"

SOURCES = {
    "sports": "espn: site.api.espn.com/apis/site/v2/sports/<league>/scoreboard (today's board only)",
    "perps": "okx, hyperliquid, kraken futures, deribit (ltcm/data/derivs.py Derivatives.snapshot)",
    "vol": "deribit: www.deribit.com/api/v2/public/get_volatility_index_data (resolution 3600: hourly DVOL candles)",
    "funding": "okx: www.okx.com/api/v5/public/funding-rate-history (<COIN>-USDT-SWAP, settled rates)",
}
CADENCE = {
    "sports": "every 60 s while a game of the league is live or starts within 90 minutes, else every 15 minutes",
    "perps": "every 5 minutes",
    "vol": "hourly, 90 seconds after the hour; backfilled over the replay window",
    "funding": "every 30 minutes (OKX settles at 00:00, 08:00 and 16:00 UTC); backfilled over the replay window",
}
WHAT = {
    "sports": "ESPN scoreboards: every game on the league's current board with status (pre/in/post), score, period, "
              "clock, start time, records and the sportsbook line (spread, total, moneylines)",
    "perps": "per coin: OKX (8-hour funding rate, next rate, premium, open interest in USD, last price), Hyperliquid and "
             "Kraken (1-hour funding rate, open interest, mark), Deribit DVOL (BTC and ETH only) and the OKX funding z-score",
    "vol": "Deribit DVOL, the 30-day implied volatility index in annualized percent, for BTC and ETH: each completed hourly "
           "candle (open, high, low, close) stamped at its close, with change_24h (the close minus the close 24 hours before)",
    "funding": "per coin: OKX's settled perpetual funding rate (<COIN>-USDT-SWAP), a row per settlement stamped at its "
               "fundingTime, with interval_hours, avg_24h, avg_7d and zscore_30d computed only from rates settled at or before it",
}
POINT_IN_TIME = {
    "sports": "each row is stamped with the House's receive time and shown only from then on, live and in replay; nothing "
              "is backfilled, and ESPN is never asked for a past date",
    "perps": "each row is stamped with the House's receive time and shown only from then on, live and in replay; nothing "
             "is backfilled",
    "vol": "each row is a completed hourly DVOL candle stamped at its close and shown only from then on, live and in replay; "
           "the history before recording began is backfilled from Deribit's own candles and stamped the same way, never "
           "with the time it was fetched, and a candle still open is never stored",
    "funding": "each row is a settled OKX funding rate stamped at its settlement (fundingTime) and shown only from then on, "
               "live and in replay; the history before recording began is backfilled from OKX's settled history and "
               "stamped the same way, and its averages and z-score read only rates settled at or before it",
}

#: Kalshi sports series prefix -> the league key a strategy names in `NEEDS["feeds"]["sports"]`.
#: The longest matching prefix wins. Only leagues whose ESPN scoreboard path is known are here; a
#: series none of them names is unmapped and its scoreboard unavailable (esports, cricket, tennis,
#: UFC and the smaller football leagues, Sept 22, 2026).
SPORTS_SERIES: tuple[tuple[str, str], ...] = (
    ("KXNFL", "nfl"), ("KXNCAAF", "ncaaf"), ("KXMLB", "mlb"), ("KXWNBA", "wnba"), ("KXNBA", "nba"), ("KXNHL", "nhl"),
    ("KXMLS", "mls"), ("KXEPL", "epl"), ("KXLALIGA", "laliga"), ("KXSERIEA", "seriea"), ("KXBUNDESLIGA", "bundesliga"),
    ("KXLIGUE1", "ligue1"), ("KXEFLCHAMPIONSHIP", "championship"), ("KXLIGAMX", "ligamx"), ("KXEREDIVISIE", "eredivisie"),
    ("KXLIGAPORTUGAL", "ligaportugal"), ("KXSCOTTISHPREM", "scottishprem"),
)
#: League key -> ESPN site-API path (`ltcm.data.sports.league_path` takes a sport/league path as is;
#: the first eight are its own LEAGUES table, the rest ESPN's league codes).
SPORTS_LEAGUES: dict[str, str] = {
    "nfl": "football/nfl", "ncaaf": "football/college-football", "mlb": "baseball/mlb", "wnba": "basketball/wnba",
    "nba": "basketball/nba", "nhl": "hockey/nhl", "mls": "soccer/usa.1", "epl": "soccer/eng.1",
    "laliga": "soccer/esp.1", "seriea": "soccer/ita.1", "bundesliga": "soccer/ger.1", "ligue1": "soccer/fra.1",
    "championship": "soccer/eng.2", "ligamx": "soccer/mex.1", "eredivisie": "soccer/ned.1",
    "ligaportugal": "soccer/por.1", "scottishprem": "soccer/sco.1",
}
#: A Kalshi crypto series names its coin between `KX` and an optional `D` (daily) or `15M` suffix.
#: (A coin ending in D would read wrongly as a daily series -- none trades on Kalshi, Sept 22, 2026.)
_KALSHI_COIN = re.compile(r"^KX([A-Z]{2,5}?)(?:D|15M)?$")
PERP_ALIASES = {"XBT": "BTC"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (feed TEXT NOT NULL, key TEXT NOT NULL, received REAL NOT NULL, started REAL NOT NULL,
    digest TEXT NOT NULL, payload BLOB NOT NULL, PRIMARY KEY (feed, key, received));
CREATE TABLE IF NOT EXISTS polls (feed TEXT NOT NULL, key TEXT NOT NULL, started REAL NOT NULL, finished REAL NOT NULL,
    ok INTEGER NOT NULL, changed INTEGER NOT NULL, error TEXT);
CREATE INDEX IF NOT EXISTS polls_by_key ON polls(feed, key, ok, finished);
CREATE TABLE IF NOT EXISTS backfills (feed TEXT NOT NULL, key TEXT NOT NULL, source TEXT NOT NULL, target REAL NOT NULL,
    began REAL NOT NULL, updated REAL NOT NULL, pages INTEGER NOT NULL, stored INTEGER NOT NULL, oldest REAL, newest REAL,
    done INTEGER NOT NULL, exhausted INTEGER NOT NULL, error TEXT, PRIMARY KEY (feed, key));
"""


# ------------------------------------------------------------------------------ small helpers
def stamp(ts: float) -> str:
    """A time as the House writes one (`ledger.now_iso`: UTC, milliseconds)."""
    whole = math.floor(float(ts))
    millis = int(round((float(ts) - whole) * 1000.0))
    if millis >= 1000:
        whole, millis = whole + 1, millis - 1000
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(whole)) + f".{millis:03d}Z"


def _epoch(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()


def _received(ts: float) -> float:
    """The House's clock rounded UP to the millisecond: a row never reads as received before it was."""
    return math.ceil(float(ts) * 1000.0) / 1000.0


def _aligned(now: float, every: float, offset: float = HISTORY_OFFSET) -> float:
    """The first moment after `now` that is `offset` seconds past a multiple of `every` (UTC)."""
    return (math.floor((float(now) - offset) / every) + 1) * every + offset


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def league_of_series(series: Any) -> str | None:
    """The league a Kalshi sports series is about, by its longest mapped prefix; None when none maps it."""
    name = str(series or "").strip().upper()
    best: tuple[str, str] | None = None
    for prefix, league in SPORTS_SERIES:
        if name.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, league)
    return best[1] if best else None


def sports_plan(niches: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """(the leagues whose scoreboards to record, the sports series no league maps), from the
    universes -- busiest live series first, then the listed ones -- of the open Kalshi sports desks."""
    leagues: list[str] = []
    unmapped: list[str] = []
    for niche in niches.values():
        if getattr(niche, "venue", "") != "kalshi" or str(getattr(niche, "category", "")) != "Sports" or getattr(niche, "dormant", False):
            continue
        for series in getattr(niche, "universe", ()):
            league = league_of_series(series)
            if league is None:
                if series not in unmapped:
                    unmapped.append(series)
            elif league not in leagues:
                leagues.append(league)
    return leagues, unmapped


def perp_coins(niches: Mapping[str, Any]) -> list[str]:
    """The coins the crypto desks trade: the Alpaca crypto symbols (`SOL/USD` -> SOL) and the coins
    of the Kalshi crypto series (`KXBTCD` -> BTC, `KXZEC15M` -> ZEC; `KXCRYPTOLEAD15M` names none)."""
    coins: list[str] = []
    for niche in niches.values():
        if getattr(niche, "dormant", False):
            continue
        if getattr(niche, "venue", "") == "alpaca" and getattr(niche, "asset_class", "") == "crypto":
            names = [str(s).upper().split("/", 1)[0] for s in getattr(niche, "universe", ())]
        elif getattr(niche, "venue", "") == "kalshi" and str(getattr(niche, "category", "")) == "Crypto":
            names = [m.group(1) for s in getattr(niche, "universe", ()) if (m := _KALSHI_COIN.match(str(s).upper()))]
        else:
            continue
        for coin in names:
            coin = PERP_ALIASES.get(coin, coin)
            if coin and coin not in coins:
                coins.append(coin)
    return coins


@lru_cache(maxsize=1)
def known_perps() -> frozenset[str]:
    """Every coin a strategy may ask the perps (and funding) feed for: those of the desks listed in niches.json."""
    from . import niches as niches_module

    return frozenset(perp_coins(niches_module.load()))


def _sports_key(raw: Any) -> str | None:
    text = str(raw or "").strip()
    if not text or len(text) > 64:
        return None
    low = text.lower()
    if low in SPORTS_LEAGUES:
        return low
    by_path = {path: key for key, path in SPORTS_LEAGUES.items()}
    if low in by_path:
        return by_path[low]
    return league_of_series(text) if low.startswith("kx") else None


def _coin_key(raw: Any, known: frozenset[str] | tuple[str, ...]) -> str | None:
    """A coin as the perps, funding and vol feeds name it (`BTC`), from `BTC/USD`, `btc-usdt`, `XBT`,
    `BTCUSD` or `BTCPERP` -- when it is one of `known`; None otherwise."""
    text = str(raw or "").strip().upper()
    if not text or len(text) > 32:
        return None
    coin = re.split(r"[/\-_: ]", text, maxsplit=1)[0]
    coin = PERP_ALIASES.get(coin, coin)
    if coin in known:
        return coin
    for suffix in ("USDT", "USDC", "USD", "PERP", "DVOL"):  # BTCUSD, BTCPERP, BTCDVOL
        if coin.endswith(suffix) and PERP_ALIASES.get(coin[: -len(suffix)], coin[: -len(suffix)]) in known:
            return PERP_ALIASES.get(coin[: -len(suffix)], coin[: -len(suffix)])
    return None


def _perps_key(raw: Any) -> str | None:
    return _coin_key(raw, known_perps())


def requested(value: Any) -> dict[str, list[str]]:
    """`NEEDS["feeds"]` held to what the House can record: known feed names only (`sports`,
    `perps`, `vol`, `funding`, and the recorders of Sept 24, 2026 in `RECORDERS`), at most
    `MAX_KEYS` keys each in the order declared, league names in lower case (`nfl`, or a Kalshi
    series such as `KXNFLGAME`, or an ESPN path) and coins in upper case (`BTC`, `BTC/USD`, `XBT`);
    each recorder's own keys in its own spelling (`Source.key_of`: a settlement station `KNYC` from
    `KXHIGHNY`, a ticker `AAPL`, a tenor `10Y` ...). A league no Kalshi series maps, a coin no crypto
    desk trades, a DVOL other than BTC's and ETH's and a key a recorder does not know are dropped,
    never guessed. Anything else yields {}. A keyed recorder's name is kept whether or not the owner
    has placed its key: an absent key only means its rows are absent."""
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, list[str]] = {}
    for feed, keys in value.items():
        name = str(feed or "").strip().lower()
        if name not in FEEDS:
            continue
        if isinstance(keys, str):
            keys = [keys]
        if not isinstance(keys, (list, tuple)):
            continue
        kept = out.setdefault(name, [])
        for raw in keys:
            if len(kept) >= MAX_KEYS:
                break
            if name in RECORDERS:
                key = RECORDERS[name].key_of(raw)
            else:
                key = _sports_key(raw) if name == "sports" else _coin_key(raw, VOL_KEYS) if name == "vol" else _perps_key(raw)
            if key is not None and key not in kept:
                kept.append(key)
    return {name: keys for name, keys in out.items() if keys}


# ---------------------------------------------------------------------------- tool requests
_SCORE_WORDS = frozenset(("score", "scores", "scoreboard", "scoreboards", "livescore", "livescores"))
_SPORTS_CONTEXT = frozenset(("live", "sport", "sports", "espn", "game", "games", "ingame", "inplay",
                             "football", "baseball", "basketball", "hockey", "soccer", *SPORTS_LEAGUES))
_PERPS_CONTEXT = frozenset(("rate", "rates", "perp", "perps", "perpetual", "perpetuals", "swap", "swaps", "crypto", "oi",
                            "okx", "hyperliquid", "kraken", "binance", "bybit", "deribit"))
_DERIVATIVES = frozenset(("perp", "perps", "perpetual", "perpetuals", "swap", "swaps", "futures", "derivatives"))
#: Words that ask for history. Only `vol` and `funding` hold any: a request for the history of
#: anything else is still for something the House does not record.
_HISTORY = frozenset(("history", "historical", "backfill", "archive", "archived"))
_SETTLED = frozenset(("settled", "settlement", "settlements"))
_VOL_WORDS = frozenset(("vol", "vols", "volatility", "iv"))
_VOL_COINS = frozenset(("btc", "eth", "bitcoin", "ethereum", "ether", "crypto", "deribit"))
#: Words that make a request about something the House does not record: line-ups, injuries,
#: player props, history before recording began, or a sport no scoreboard here covers.
_NOT_FEEDS = frozenset(("lineup", "lineups", "injury", "injuries", "inactive", "inactives", "prop", "props", "player",
                        "players", "tennis", "atp", "wta", "cricket", "esports", "lol", "cs2", "dota", "dota2", "valorant",
                        "ufc", "mma", "golf", "f1", "nascar", "boxing", "ncaab", *_HISTORY))


def request_feed(name: Any) -> str | None:
    """The feed a `tool.request` name plainly asks for, or None. Conservative on purpose: the
    name (as `Commons.request_tool` stores it) must name live scores or a scoreboard with a sports
    word, perpetual funding or open interest with a derivatives word (a Kalshi market's open
    interest is not a perp's), Deribit's DVOL or a crypto implied volatility (`vol`), the history of
    perpetual funding (`funding`), or what a recorder of Sept 24, 2026 records, in its own words
    (`Source.asks`: a weather ensemble, a forecast's history, an 8-K's acceptance, SOFR ...). A
    request for the history of anything else is for something the House does not hold."""
    words = set(re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_").split("_")) - {""}
    if not words or words & (_NOT_FEEDS - _HISTORY):
        return None
    if "dvol" in words or ("implied" in words and words & _VOL_WORDS and words & _VOL_COINS):
        return "vol"
    if "funding" in words and words & _PERPS_CONTEXT:
        return "funding" if words & (_HISTORY | _SETTLED) else "perps"
    for feed, source in RECORDERS.items():  # the recorders of Sept 24, 2026, each by its own words
        if source.asks(words) and (source.history or not words & _HISTORY):  # a live feed holds no history
            return feed
    if words & _HISTORY:
        return None
    if (("open" in words and "interest" in words) or "oi" in words) and words & _DERIVATIVES:
        return "perps"
    if words & _SCORE_WORDS and words & _SPORTS_CONTEXT:
        return "sports"
    if {"game", "state"} <= words and words & {"live", "sport", "sports", "ingame", "inplay", *SPORTS_LEAGUES}:
        return "sports"
    return None


def _hot(events: Sequence[Mapping[str, Any]] | None, now: float) -> bool:
    """Is a game on this board live, or due to start within `SPORTS_SOON_SECONDS`? A game still
    `pre` after its start time (a delay) counts for three hours."""
    for event in events or []:
        status = str((event or {}).get("status") or "")
        if status == "in":
            return True
        if status == "pre" and event.get("start"):
            try:
                start = _epoch(event["start"])
            except (TypeError, ValueError):
                continue
            if now - 3 * 3600 <= start <= now + SPORTS_SOON_SECONDS:
                return True
    return False


def _thin(times: Sequence[float], width: float, *, keep_first: bool) -> list[int]:
    """At most one row a step: of the rows received in one step ((k - 1) * width, k * width] only
    the last, since no step on that grid could show an earlier one. `keep_first` keeps the row that
    opens the window (received at or before its start) whatever follows it."""
    picked: list[int] = []
    bucket = None
    for index, at in enumerate(times):
        this = math.ceil(at / width)
        if picked and this == bucket and not (keep_first and picked[-1] == 0):
            picked[-1] = index
        else:
            picked.append(index)
        bucket = this
    return picked


# ------------------------------------------------------------------ the history feeds' rows
def _vol_rows(rows: Sequence[tuple[float, Mapping[str, Any]]]) -> list[tuple[float, dict[str, Any]]]:
    """DVOL candles, oldest first, with `change_24h`: the close minus the close of the candle that
    closed exactly 24 hours earlier when the store holds it, else None. Only earlier rows are read."""
    closes: dict[int, float] = {}
    out: list[tuple[float, dict[str, Any]]] = []
    for at, payload in rows:
        close = _num(payload.get("close"))
        prior = closes.get(int(round(at)) - 86400)
        change = round(close - prior, 6) if close is not None and prior is not None else None
        out.append((at, {**payload, "change_24h": change}))
        if close is not None:
            closes[int(round(at))] = close
    return out


def _funding_rows(rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
    """Settled funding rates, oldest first, with what a strategy reads beside each:

    - `interval_hours`: the hours since the settlement before it, when the store holds that one
      and it was at most 8 hours earlier, else 8 (OKX's usual interval; a rate is per interval,
      so it annualizes as `rate * 8760 / interval_hours`);
    - `avg_24h`, `avg_7d`: the mean of the rates settled in the 24 hours / 7 days up to and
      including this one;
    - `zscore_30d`: this rate against the rates settled in the 30 days before it
      (`ltcm.data.derivs.zscore`: None with fewer than three).

    Each reads only rows stamped at or before this one, and is None unless the history held (`since`,
    the oldest row) reaches back over its whole window: an average of two days is not a 7-day one."""
    from ltcm.data.derivs import zscore

    stamps = [at for at, _ in rows]
    rates = [_num(payload.get("rate")) for _, payload in rows]
    out: list[tuple[float, dict[str, Any]]] = []
    for i, (at, payload) in enumerate(rows):
        gap = at - stamps[i - 1] if i else None
        interval = int(round(gap / HOUR)) if gap is not None and HOUR / 2 <= gap <= 8 * HOUR + 60 else 8
        derived: dict[str, Any] = {"interval_hours": interval}
        for name, days in (("avg_24h", 1), ("avg_7d", 7)):
            values = [r for r in rates[bisect.bisect_right(stamps, at - days * 86400.0, 0, i):i + 1] if r is not None]
            reach = since is not None and since <= at - days * 86400.0
            derived[name] = round(sum(values) / len(values), 10) if reach and values else None
        base = [r for r in rates[bisect.bisect_left(stamps, at - 30 * 86400.0, 0, i):i] if r is not None]
        reach = since is not None and since <= at - 30 * 86400.0
        derived["zscore_30d"] = zscore(rates[i], base) if reach and rates[i] is not None else None
        out.append((at, {**payload, **derived}))
    return out


def _source(feed: str, key: str) -> str:
    """The endpoint a history feed's rows for `key` come from, as `backfills` records it."""
    from ltcm.data.derivs import DERIBIT_HOST, OKX_HOST

    if feed in RECORDERS:
        return RECORDERS[feed].endpoint(key)
    if feed == "vol":
        return f"{DERIBIT_HOST}/api/v2/public/get_volatility_index_data?currency={key}&resolution=3600"
    return f"{OKX_HOST}/api/v5/public/funding-rate-history?instId={key}-USDT-SWAP"


# ------------------------------------------------------------------------------ the recorder
class FeedRecorder:
    """Records the feeds and answers for them.

    `house` supplies the clock, the ledger, the alert line, the desks' universes (`house.niches`,
    live series included) and its replay windows (`House._live_window`); without one, give `clock`
    and `ledger` (and `niches`, or niches.json is read). `transports` is the HTTP transport of each
    feed's fetcher ({"sports": ..., "perps": ..., "vol": ..., "funding": ...}, or one object for all;
    tests give `ltcm.tests.fakes.FakeTransport`); None leaves each fetcher its own `HttpTransport`.
    `keys` overrides what is polled ({"sports": [...], "perps": [...], ...}). `sleep` is what pauses
    between history pages (tests give one that does not), and `backfill_pages` caps a backfill pass.
    `environ` and `allowed_hosts` stand in for the House's environment and the allowlist the
    repository records (`scripts/floor_box.py` LEAGUE_HOSTS), which switch the keyed recorders on."""

    def __init__(self, house: Any = None, path: str | Path | None = None, transports: Any = None, *,
                 clock: Callable[[], float] | None = None, ledger: Any = None, alert: Callable[[str, str], None] | None = None,
                 niches: Mapping[str, Any] | None = None, keys: Mapping[str, Sequence[str]] | None = None,
                 sleep: Callable[[float], None] | None = None, backfill_pages: int = BACKFILL_PAGES,
                 environ: Mapping[str, str] | None = None, allowed_hosts: Sequence[str] | None = None):
        if path is None:
            if house is None:
                raise ValueError("a feed store needs a path or a House")
            path = Path(house.root) / DB_NAME
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.house = house
        self.clock = clock or (house.clock if house is not None else time.time)
        self.ledger = ledger if ledger is not None else getattr(house, "ledger", None)
        self._alert = alert or (house.alert if house is not None else None)
        self._niches = niches
        self._keys = {str(feed): list(rows) for feed, rows in keys.items()} if keys is not None else None
        self._transports = transports
        self._sleep = sleep or time.sleep
        self._backfill_pages = max(1, int(backfill_pages))
        self._fetchers: dict[str, Any] = {}
        self._lock = threading.RLock()  # one writer at a time in this process, and the counters below
        self._local = threading.local()
        self._connections: list[tuple[threading.Thread, Any]] = []
        self._next: dict[tuple[str, str], float] = {}  # (feed, key) -> when it is due; perps poll as one ("perps", "*")
        self._hot: dict[str, bool] = {}  # league -> was a game live or near at its last good poll
        self._warned: dict[str, float] = {}
        self._covered: dict[str, int] = {}  # feed -> the hour whose coverage row is on the ledger
        self._stats: dict[tuple[str, str], dict[str, Any]] | None = None
        self._history: dict[tuple[str, str], dict[str, Any]] | None = None  # the `backfills` rows, read once
        self._venues: dict[str, int] = {}  # perps: coins each venue answered for in the last pass
        self._environ = environ
        self._hosts = tuple(str(h).lower() for h in allowed_hosts) if allowed_hosts is not None else None
        self._read: dict[str, tuple[float, Any]] = {}  # "env" / "hosts" -> (read at, what was read)
        self._state: dict[str, dict[str, Any]] = {}  # a recorder of Sept 24, 2026 -> what it keeps between passes
        self._closed = False
        with self._lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    @property
    def db(self) -> Any:
        """This thread's connection (as `OptionsHistory.db`): wake threads, the replay lane and the
        feeds lane read and write at once, and WAL lets readers go on while a poll is written."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            import sqlite3

            conn = sqlite3.connect(str(self.path), timeout=60, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
            with self._lock:
                for thread, old in [pair for pair in self._connections if not pair[0].is_alive()]:
                    old.close()
                self._connections = [pair for pair in self._connections if pair[0].is_alive()]
                self._connections.append((threading.current_thread(), conn))
        return conn

    def close(self) -> None:
        self._closed = True
        with self._lock:
            for _, conn in self._connections:
                conn.close()
            self._connections = []
        self._local = threading.local()

    # -- what is polled --------------------------------------------------------------------------
    def niches(self) -> Mapping[str, Any]:
        if self._niches is not None:
            return self._niches
        if self.house is not None:
            return self.house.niches
        from . import niches as niches_module

        self._niches = niches_module.load()
        return self._niches

    def keys(self, feed: str) -> list[str]:
        """What this House polls for `feed` now (the survey moves the universes, so it is asked each time).
        A keyed recorder the owner has not switched on (`waiting_for`) polls nothing."""
        if feed in RECORDERS and self.waiting_for(feed):
            return []
        if self._keys is not None:
            return list(self._keys.get(feed) or [])
        if feed == "sports":
            return sports_plan(self.niches())[0]
        if feed in ("perps", "funding"):
            return perp_coins(self.niches())
        if feed == "vol":
            return list(VOL_KEYS)
        if feed in RECORDERS:
            source = RECORDERS[feed]
            try:
                return list(source.keys(self))[:source.max_keys]
            except Exception:  # noqa: BLE001 - a universe that cannot be read polls nothing this time
                return []
        return []

    def unmapped(self) -> list[str]:
        return sports_plan(self.niches())[1]

    def _plan(self) -> list[tuple[str, str]]:
        plan = [("sports", league) for league in self.keys("sports")]
        for feed in ("perps", *HISTORY_FEEDS):
            if self.keys(feed):
                plan.append((feed, "*"))
        for feed, source in RECORDERS.items():  # the recorders of Sept 24, 2026 that are live
            if source.history:
                continue  # in HISTORY_FEEDS above
            keys = self.keys(feed)
            if keys:
                plan.extend([(feed, "*")] if source.batch else [(feed, key) for key in keys])
        if self._backfill_pending():
            plan.append(("backfill", "*"))  # last: every live poll due goes first
        return plan

    def _fetcher(self, feed: str) -> Any:
        fetcher = self._fetchers.get(feed)
        if fetcher is None:
            transport = self._transports.get(feed) if isinstance(self._transports, Mapping) else self._transports
            if feed in RECORDERS:
                fetcher = RECORDERS[feed].fetcher(transport, self.clock)
                self._fetchers[feed] = fetcher
                return fetcher
            if feed == "sports":
                from ltcm.data.sports import Sports

                fetcher = Sports(transport, timeout=TIMEOUT, clock=self.clock)
            else:
                from ltcm.data.derivs import Derivatives

                fetcher = Derivatives(transport, timeout=TIMEOUT, clock=self.clock)
            self._fetchers[feed] = fetcher
        return fetcher

    # -- the schedule ----------------------------------------------------------------------------
    def due(self) -> bool:
        """Is a league, a feed's pass or the backfill due now? Cheap, and never raises: the tick asks every minute."""
        if self._closed:
            return False
        try:
            now = self.clock()
            plan = self._plan()
            with self._lock:
                return any(self._next.get(item, 0.0) <= now for item in plan)
        except Exception:  # noqa: BLE001 - a question the tick asks must not cost the tick
            return False

    def shipped(self) -> bool:
        """Has any feed recorded anything yet?"""
        try:
            with self._lock:
                return any(row.get("first_ok") for row in self._load_stats().values())
        except Exception:  # noqa: BLE001
            return False

    def run(self) -> dict[str, Any]:
        """Poll whatever is due and record it, then backfill for what time is left. The House calls
        this on its feeds lane; it never raises: a source that fails is a failed poll, and a warning
        at most hourly."""
        out: dict[str, Any] = {"polled": [], "stored": 0, "failed": []}
        if self._closed:
            return out
        try:
            now = self.clock()
            for feed, key in self._plan():
                if self._closed:
                    break
                with self._lock:
                    if self._next.get((feed, key), 0.0) > now:
                        continue
                if feed == "sports":
                    self._poll_sports(key, out)
                elif feed == "perps":
                    self._poll_perps(out)
                elif feed == "backfill":
                    self._backfill(out)
                elif feed in HISTORY_FEEDS:
                    self._poll_history(feed, out)
                else:
                    self._poll_source(feed, key, out)
            self._after_pass(out)
        except Exception as exc:  # noqa: BLE001 - the recorder must never take its lane or the tick down
            out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            self._warn("recorder", f"the feed recorder failed a pass ({out['error']})")
        return out

    def _schedule(self, feed: str, key: str, at: float) -> None:
        with self._lock:
            self._next[(feed, key)] = at

    def _live_due(self) -> bool:
        """Has a live poll fallen due (a backfill pass gives way to it)?"""
        now = self.clock()
        plan = [item for item in self._plan() if item[0] != "backfill"]
        with self._lock:
            return any(self._next.get(item, 0.0) <= now for item in plan)

    def _poll_sports(self, league: str, out: dict[str, Any]) -> None:
        path = SPORTS_LEAGUES.get(league)
        started = self.clock()
        events, error = None, None
        # Due again soon in any case, so a store that cannot be written does not hammer ESPN.
        self._schedule("sports", league, started + (SPORTS_LIVE_SECONDS if self._hot.get(league) else RETRY_SECONDS))
        try:
            if path is None:
                raise ValueError(f"no ESPN scoreboard is mapped for {league!r}")
            # The current board only, always: a `dates` query would hand a replay the final score.
            events = self._fetcher("sports").scoreboard(path)
        except Exception as exc:  # noqa: BLE001 - a scoreboard that fails is a failed poll
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
        finished = self.clock()
        if events is not None:
            hot = _hot(events, finished)
            with self._lock:
                self._hot[league] = hot
            self._schedule("sports", league, finished + (SPORTS_LIVE_SECONDS if hot else SPORTS_QUIET_SECONDS))
        payload = {"league": league, "espn": path, "events": events} if events is not None else None
        stored = self.record("sports", league, started=started, finished=finished, payload=payload, error=error)
        out["polled"].append(f"sports:{league}")
        out["stored"] += int(stored)
        if error:
            out["failed"].append(("sports", league, error))

    def _poll_perps(self, out: dict[str, Any]) -> None:
        coins = self.keys("perps")
        started = self.clock()
        self._schedule("perps", "*", started + PERPS_SECONDS)
        rows, error = [], None
        try:
            rows = list(self._fetcher("perps").snapshot(coins) or [])
        except Exception as exc:  # noqa: BLE001 - every venue down at once is a failed poll of every coin
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
        finished = self.clock()
        by_coin = {str(row.get("symbol") or "").upper(): row for row in rows if isinstance(row, Mapping)}
        venues = {"okx": 0, "hyperliquid": 0, "kraken": 0}
        for coin in coins:
            row = by_coin.get(coin)
            answered = [venue for venue in venues if row is not None and row.get(venue) is not None]
            for venue in answered:
                venues[venue] += 1
            # `as_of` is the fetch's own clock, which the receive stamp `t` replaces (and which
            # would make every poll look new).
            payload = {k: v for k, v in row.items() if k != "as_of"} if answered else None
            why = error or (None if answered else f"no venue answered for {coin}")
            stored = self.record("perps", coin, started=started, finished=finished, payload=payload, error=why)
            out["stored"] += int(stored)
            if why:
                out["failed"].append(("perps", coin, why))
        out["polled"].append("perps")
        with self._lock:
            self._venues = venues if coins else {}

    # -- the history feeds: live polls ------------------------------------------------------------
    def _poll_history(self, feed: str, out: dict[str, Any]) -> None:
        """One pass of a history feed (`vol`, `funding`, and the history recorders of Sept 24, 2026):
        for each key, every completed candle, settled rate or final row newer than the newest row
        held (`_fetch_head`), stamped when it became final. Scheduled 90 seconds past the next hour
        (vol) or half hour (funding), or at the recorder's own cadence, or sooner when a key failed."""
        every, offset = _cadence(feed)
        started = self.clock()
        self._schedule(feed, "*", started + RETRY_SECONDS)  # due again soon in any case, pushed out below
        failed = False
        asked = 0
        for key in self.keys(feed):
            if self._closed:
                break
            began = self.clock()
            if self._unlisted_now(feed, key, began):
                continue
            if asked and feed == "funding":
                self._sleep(OKX_PAUSE)
            asked += 1
            stored, error = 0, None
            try:
                stored = self._fetch_head(feed, key, began)
            except Exception as exc:  # noqa: BLE001 - a venue that fails is a failed poll of that key
                error = f"{type(exc).__name__}: {str(exc)[:300]}"
            self._note(feed, key, started=began, finished=self.clock(), ok=error is None, changed=stored > 0, error=error)
            out["stored"] += stored
            if error:
                out["failed"].append((feed, key, error))
                failed = failed or not _unlisted(error)
        out["polled"].append(feed)
        finished = self.clock()
        nxt = _aligned(finished, every, offset)
        self._schedule(feed, "*", min(nxt, finished + RETRY_SECONDS) if failed else nxt)

    def _fetch_head(self, feed: str, key: str, now: float) -> int:
        """Store what is newer than the newest row held: one page when nothing is held yet (the
        backfill fetches the rest), else pages back from now until they meet that row -- so a House
        that was down for a day fills the day, and the history never has a hole. Raises when the
        venue fails. Returns how many rows were new."""
        with self._lock:
            newest = (self._load_stats().get((feed, key)) or {}).get("last_ok")
        target = self._target_of(feed, key, now)
        floor = target if newest is None else max(float(newest), target)
        stored, before = 0, None
        for page_number in range(1 if newest is None else HEAD_PAGES):
            if page_number:
                self._sleep(OKX_PAUSE)
            limit = FUNDING_PAGE if newest is None else min(FUNDING_PAGE, 10 + int(max(0.0, now - float(newest)) // HOUR))
            page = self._page(feed, key, before=before, floor=floor, now=now, limit=limit)
            stored += self._store_history(feed, key, page["rows"], fetched=now)
            if newest is None or page["reached"] or page["exhausted"] or not page["rows"]:
                break
            before = min(at for at, _ in page["rows"])
        return stored

    def _page(self, feed: str, key: str, *, before: float | None, floor: float, now: float, limit: int = FUNDING_PAGE) -> dict[str, Any]:
        """One request of settled history for `key`: the rows that became final strictly before
        `before` (None: at or before `now`) and at or after `floor`, as (stamp, payload) -- plus
        `reached` (the answer reaches down to `floor`) and `exhausted` (the venue has nothing older).
        Raises when the venue fails."""
        if feed in RECORDERS:
            return RECORDERS[feed].page(self._fetcher(feed), key, before=before, floor=floor, now=now, recorder=self)
        if feed == "vol":
            top = now if before is None else before - HOUR  # the last candle OPEN asked for
            end_ms = math.floor(top * 1000.0) - (0 if before is None else 1)
            start_open = max(floor - HOUR, top - VOL_PAGE_HOURS * HOUR)
            start_ms = math.ceil(start_open * 1000.0)
            if end_ms < start_ms:
                return {"rows": [], "reached": True, "exhausted": False}
            candles, more = self._fetcher("vol").dvol_candles(key, start_ms, end_ms)
            more = more if more is not None and more > start_ms else None  # older candles of this range remain
            rows = []
            for candle in candles:
                close = candle["t_ms"] / 1000.0 + HOUR
                if close > now or close < floor or (before is not None and close >= before):
                    continue  # still open, or outside what was asked
                rows.append((close, {"open": candle["open"], "high": candle["high"], "low": candle["low"],
                                     "close": candle["close"], "hours": 1}))
            reached = more is None and start_open <= floor - HOUR
            return {"rows": rows, "reached": reached, "exhausted": not candles and not reached}
        settled = self._fetcher("funding").okx_funding_settled(key, after_ms=None if before is None else int(round(before * 1000.0)),
                                                               limit=limit)
        rows = [(item["time_ms"] / 1000.0, {"rate": item["rate"]}) for item in settled]
        rows = [(at, payload) for at, payload in rows if at <= now and (before is None or at < before)]
        oldest = min((at for at, _ in rows), default=None)
        reached = oldest is not None and oldest <= floor
        return {"rows": [(at, payload) for at, payload in rows if at >= floor], "reached": reached,
                "exhausted": len(settled) < limit and not reached}

    # -- the history feeds: the backfill ----------------------------------------------------------
    def backfill_days(self) -> float:
        """How many days back the history feeds reach: the House's longest live replay window of an
        hourly strategy (Alpaca `replay_days`, Kalshi `kalshi_replay_days`) or a Kalshi daily one
        (`kalshi_replay_days` x 7) plus `BACKFILL_MARGIN_DAYS`, and never less than `BACKFILL_DAYS`."""
        windows = self._windows()
        spans = [seconds / 86400.0 for (venue, horizon), seconds in windows.items() if not (venue == "alpaca" and horizon == "day")]
        return max([float(BACKFILL_DAYS)] + [span + BACKFILL_MARGIN_DAYS for span in spans])

    def _windows(self) -> dict[tuple[str, str], float]:
        """The House's live replay window of each (venue, horizon), in seconds (`House._live_window`);
        none without a House (or one that cannot say), and then `BACKFILL_DAYS` is the backfill."""
        out: dict[tuple[str, str], float] = {}
        window = getattr(self.house, "_live_window", None)
        if not callable(window):
            return out
        for venue in ("alpaca", "kalshi"):
            for horizon in ("hour", "day"):
                try:
                    start, end = window({"venue": venue, "horizon": horizon})
                    out[(venue, horizon)] = max(0.0, float(end) - float(start))
                except Exception:  # noqa: BLE001 - a window that cannot be read is left out
                    continue
        return out

    def _wanted_target(self, feed: str, now: float) -> float:
        own = RECORDERS[feed].backfill_days if feed in RECORDERS else None
        return now - ((own or self.backfill_days()) + LOOKBACK_DAYS.get(feed, 0)) * 86400.0

    def _history_state(self) -> dict[tuple[str, str], dict[str, Any]]:
        """The `backfills` rows by (feed, key), read from the store once and kept current here."""
        with self._lock:
            if self._history is None:
                self._history = {
                    (feed, key): {"source": source, "target": target, "began": began, "updated": updated, "pages": int(pages),
                                  "stored": int(stored), "oldest": oldest, "newest": newest, "done": bool(done),
                                  "exhausted": bool(exhausted), "error": error}
                    for feed, key, source, target, began, updated, pages, stored, oldest, newest, done, exhausted, error in self.db.execute(
                        "SELECT feed, key, source, target, began, updated, pages, stored, oldest, newest, done, exhausted, error "
                        "FROM backfills")}
            return self._history

    def _history_row(self, feed: str, key: str, now: float) -> dict[str, Any]:
        """This key's `backfills` row, begun now if it has none (its target fixed from now)."""
        with self._lock:
            state = self._history_state()
            row = state.get((feed, key))
            if row is None:
                row = {"source": _source(feed, key), "target": self._wanted_target(feed, now), "began": now, "updated": now,
                       "pages": 0, "stored": 0, "oldest": None, "newest": None, "done": False, "exhausted": False, "error": None}
                state[(feed, key)] = row
                self._save_history(feed, key)
            return row

    def _save_history(self, feed: str, key: str) -> None:
        with self._lock:
            row = self._history_state()[(feed, key)]
            self.db.execute("INSERT OR REPLACE INTO backfills VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (feed, key, row["source"], float(row["target"]), float(row["began"]), float(row["updated"]),
                             int(row["pages"]), int(row["stored"]), row["oldest"], row["newest"], int(bool(row["done"])),
                             int(bool(row["exhausted"])), row["error"]))
            self.db.commit()

    def _target_of(self, feed: str, key: str, now: float) -> float:
        """The oldest stamp this key's backfill reaches for: fixed when it began, and moved back
        only when the House's replay windows grow (a `replay_days` raised), which reopens it."""
        wanted = self._wanted_target(feed, now)
        with self._lock:
            row = self._history_row(feed, key, now)
            if wanted < float(row["target"]) - 86400.0:
                row["target"], row["done"] = wanted, bool(row["exhausted"])
                self._save_history(feed, key)
            return float(row["target"])

    def _unlisted_now(self, feed: str, key: str, now: float) -> bool:
        """Did the source answer, less than `UNLISTED_SECONDS` ago, that it lists no such key (OKX:
        no such instrument; a recorder of Sept 24, 2026: `NOT_LISTED`)?"""
        with self._lock:
            row = self._history_state().get((feed, key))
        return bool(row) and _unlisted(row.get("error")) and now - float(row.get("updated") or 0.0) < UNLISTED_SECONDS

    def _backfill_pending(self) -> bool:
        """Is any history key polled here still short of its target (and not unlisted)?"""
        now = self.clock()
        with self._lock:
            state = self._history_state()
        for feed in HISTORY_FEEDS:
            keys = self.keys(feed)
            if not keys:
                continue
            wanted = self._wanted_target(feed, now)
            for key in keys:
                row = state.get((feed, key))
                if row is None:
                    return True
                if self._unlisted_now(feed, key, now):
                    continue
                if not row["done"] or (not row["exhausted"] and wanted < float(row["target"]) - 86400.0):
                    return True
        return False

    def _backfill(self, out: dict[str, Any]) -> None:
        """One backfill pass: pages back from the oldest row of each history key until it reaches its
        target or the venue has nothing older -- at most `self._backfill_pages` pages and
        `BACKFILL_RUN_SECONDS`, `BACKFILL_PAUSE` apart, giving way the moment a live poll is due.
        A venue that fails ends its feed's part of the pass, and the next pass waits `RETRY_SECONDS`
        instead of a minute."""
        self._schedule("backfill", "*", self.clock() + BACKFILL_SECONDS)
        if not self._backfill_walk(out):
            self._schedule("backfill", "*", self.clock() + RETRY_SECONDS)

    def _backfill_walk(self, out: dict[str, Any]) -> bool:
        """The pages of one backfill pass. False when one of them failed."""
        deadline = time.monotonic() + BACKFILL_RUN_SECONDS
        pages, clean = 0, True
        for feed in HISTORY_FEEDS:
            for key in self.keys(feed):
                ok = True
                while ok and not self._closed:
                    now = self.clock()
                    if self._unlisted_now(feed, key, now):
                        break
                    target = self._target_of(feed, key, now)  # reopens a key whose target moved back
                    with self._lock:
                        row = self._history_row(feed, key, now)
                        oldest = (self._load_stats().get((feed, key)) or {}).get("first_ok")
                        if not row["done"] and oldest is not None and float(oldest) <= target:
                            row["done"] = True  # its rows already reach the target: nothing to ask
                            self._save_history(feed, key)
                        if row["done"]:
                            break
                    if pages >= self._backfill_pages or time.monotonic() >= deadline:
                        return clean
                    if pages:
                        self._sleep(BACKFILL_PAUSE)
                        if self._live_due() or self._closed:
                            return clean  # the next run polls it, then goes on from here
                    ok = self._backfill_page(feed, key, out)
                    pages += 1
                    clean = clean and ok
                if not ok:
                    break
        return clean

    def _backfill_page(self, feed: str, key: str, out: dict[str, Any]) -> bool:
        """One page older than the oldest row held (the newest page when none is), stored with each
        row's own stamp; the key's `backfills` row says how far it has come. False when it failed."""
        started = self.clock()
        target = self._target_of(feed, key, started)
        with self._lock:
            oldest = (self._load_stats().get((feed, key)) or {}).get("first_ok")
        page, stored, error = None, 0, None
        try:
            page = self._page(feed, key, before=oldest, floor=target, now=started)
            stored = self._store_history(feed, key, page["rows"], fetched=started)
        except Exception as exc:  # noqa: BLE001 - a venue that fails is a failed poll
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
        self._note(feed, key, started=started, finished=self.clock(), ok=error is None, changed=stored > 0, error=error)
        with self._lock:
            row = self._history_row(feed, key, started)
            row["pages"] += 1
            if page is not None:
                now_oldest = (self._load_stats().get((feed, key)) or {}).get("first_ok")
                progressed = now_oldest is not None and (oldest is None or now_oldest < oldest)
                if page["reached"] or (now_oldest is not None and now_oldest <= target):
                    row["done"] = True
                elif page["exhausted"] or not progressed:
                    row["done"] = row["exhausted"] = True  # the venue's history ends here
            self._save_history(feed, key)
        out["polled"].append(f"backfill:{feed}:{key}")
        out["stored"] += stored
        if error:
            out["failed"].append((feed, key, error))
        return error is None

    # -- the recorders of Sept 24, 2026: live polls ------------------------------------------------
    def state(self, feed: str) -> dict[str, Any]:
        """What a recorder keeps between its passes on this House (the runs it last saw ...)."""
        with self._lock:
            return self._state.setdefault(feed, {})

    def _urgent_due(self) -> bool:
        """Is a scoreboard or the perps pass due? A recorder of Sept 24, 2026 gives way to them
        between its keys: the feeds lane has one slot, and a live game's minute matters more than a
        forecast's."""
        now = self.clock()
        with self._lock:
            upcoming = dict(self._next)
        if any(upcoming.get(("sports", league), 0.0) <= now for league in self.keys("sports")):
            return True
        return bool(self.keys("perps")) and upcoming.get(("perps", "*"), 0.0) <= now

    def _poll_source(self, feed: str, key: str, out: dict[str, Any]) -> bool:
        """One live poll of a recorder of Sept 24, 2026 -- one key, or every key at once for a batch
        source -- kept under the House's receive time (`record`): its content only when it changed, a
        failed poll as a `polls` row with its error and nothing stored. A source may answer
        `UNCHANGED` for a key whose content it has confirmed is still the newest (the weather
        ensemble, when no newer model run exists): a successful poll that stores nothing. Returns
        False, leaving the key due, when it gave way to a scoreboard or the perps pass."""
        source = RECORDERS[feed]
        if self._urgent_due():
            return False
        keys = self.keys(feed) if source.batch else [key]
        started = self.clock()
        self._schedule(feed, key, started + RETRY_SECONDS)  # due again soon in any case, pushed out below
        try:
            results = dict(source.poll(self._fetcher(feed), keys, self, started) or {})
        except Exception as exc:  # noqa: BLE001 - a source that fails is a failed poll of every key asked
            results = {k: exc for k in keys}
        finished = self.clock()
        clean = True
        for name in keys:
            result = results.get(name, LookupError(f"the source answered nothing for {name}"))
            if result is UNCHANGED:
                self._confirm(feed, name, started=started, finished=finished)
                continue
            if isinstance(result, BaseException):
                error = source.redact(f"{type(result).__name__}: {str(result)[:300]}", self)
                self.record(feed, name, started=started, finished=finished, error=error)
                out["failed"].append((feed, name, error))
                clean = clean and _unlisted(error)
                continue
            out["stored"] += int(self.record(feed, name, started=started, finished=finished, payload=result))
        out["polled"].append(feed if source.batch else f"{feed}:{key}")
        self._schedule(feed, key, finished + (source.every if clean else min(source.every, RETRY_SECONDS)))
        return True

    def _confirm(self, feed: str, key: str, *, started: float, finished: float) -> None:
        """A successful poll that found the key's newest content unchanged without fetching it again
        (`UNCHANGED`): its `polls` row, and nothing stored."""
        if self._closed:
            return
        received = _received(finished)
        with self._lock:
            stats = self._load_stats()  # before this poll is written, or it would be counted twice
            self.db.execute("INSERT INTO polls VALUES (?, ?, ?, ?, ?, ?, ?)", (feed, key, float(started), received, 1, 0, None))
            self.db.commit()
            row = stats.setdefault((feed, key), _empty_stats())
            row["polls"] += 1
            row["ok"] += 1
            row["last_poll"] = row["last_ok"] = row["last_good"] = received
            row["last_error"] = None

    def failing(self, feed: str, key: str) -> bool:
        """Did the key's last poll fail?"""
        with self._lock:
            return bool((self._load_stats().get((feed, key)) or {}).get("last_error"))

    def waiting_for(self, feed: str) -> str | None:
        """Why a keyed recorder (`Source.env`: The Odds API's, EIA's) polls nothing yet -- the owner
        has not placed its key in the House's environment, or its host is not on the allowlist the
        repository records -- or None when it may poll (and for every recorder that needs no key).
        Waiting is not failing: nothing is polled and nothing is said to have failed."""
        source = RECORDERS.get(feed)
        if source is None or not source.env:
            return None
        if not self.owner_key(source.env):
            return f"waiting for the owner's key: {source.env} in the House's .env (never in the repository)"
        if source.host not in self._allowed_hosts():
            return (f"waiting for the owner to allow {source.host}: scripts/floor_box.py hosts --add {source.host}, "
                    "and the host in its LEAGUE_HOSTS")
        return None

    def owner_key(self, name: str) -> str:
        """The owner's key `name` from the House's environment, or from its `.env` (`LEAGUE_ENV`, else
        the repository's), read again every `ENV_SECONDS`: a key the owner places goes live without a
        restart. Never logged, never stored (`Source.redact` takes it out of every error)."""
        if self._environ is not None:
            return str(self._environ.get(name) or "").strip()
        import os

        value = os.environ.get(name, "").strip()
        if value:
            return value
        now = time.monotonic()
        with self._lock:
            read = self._read.get("env")
        if read is None or now - read[0] >= ENV_SECONDS:
            found: dict[str, str] = {}
            try:
                path = Path(os.environ.get("LEAGUE_ENV") or REPO_ROOT / ".env")
                if path.exists():
                    for line in path.read_text(encoding="utf-8").splitlines():
                        if "=" in line and not line.lstrip().startswith("#"):
                            left, right = line.split("=", 1)
                            found[left.strip()] = right.strip().strip('"').strip("'")
            except Exception:  # noqa: BLE001 - an unreadable file is a key not placed
                found = {}
            read = (now, found)
            with self._lock:
                self._read["env"] = read
        return str(read[1].get(name) or "").strip()

    def _allowed_hosts(self) -> tuple[str, ...]:
        """The hosts the House box may reach, as the repository records them (`scripts/floor_box.py`
        LEAGUE_HOSTS, read without importing the deploy tool), re-read every `ENV_SECONDS`."""
        if self._hosts is not None:
            return self._hosts
        now = time.monotonic()
        with self._lock:
            read = self._read.get("hosts")
        if read is None or now - read[0] >= ENV_SECONDS:
            read = (now, league_hosts())
            with self._lock:
                self._read["hosts"] = read
        return read[1]

    def _searched_seconds(self, feed: str, key: str, start: float, end: float, gap: float) -> float:
        """A sparse history's coverage (8-Ks): the span its listing has been searched, from its
        backfill's target -- or from the start of the source's history when the listing ended first
        -- to its last good poll and `gap` more. Nothing until the backfill has searched back that far:
        a quarter without an 8-K is only "no 8-K" once the listing has been read over it."""
        with self._lock:
            row = dict(self._history_state().get((feed, key)) or {})
            last = (self._load_stats().get((feed, key)) or {}).get("last_good")
        if not row.get("done") or last is None:
            return 0.0
        reach = float("-inf") if row.get("exhausted") else float(row["target"])
        return max(0.0, min(end, float(last) + gap) - max(start, reach))

    # -- the store -------------------------------------------------------------------------------
    def record(self, feed: str, key: str, *, started: float, finished: float, payload: Any = None, error: str | None = None) -> bool:
        """Keep one poll of a live feed (`sports`, `perps`): always its `polls` row; its content only
        when it differs from the key's last snapshot. `finished` -- the House's clock once the fetch
        returned, rounded up to the millisecond -- is the content's availability stamp. Returns
        whether a snapshot was stored. (`vol` and `funding` rows go through `_store_history`.)"""
        if self._closed:
            return False  # a pass still in flight when the House closed writes nothing after it
        received = _received(finished)
        ok = payload is not None and not error
        text = digest = None
        if ok:
            try:
                text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
            except (TypeError, ValueError) as exc:
                ok, error = False, f"unrecordable content ({type(exc).__name__}: {str(exc)[:120]})"
        changed = False
        with self._lock:
            stats = self._load_stats()  # before this poll is written, or it would be counted twice
            db = self.db
            if ok:
                last = db.execute("SELECT digest FROM snapshots WHERE feed = ? AND key = ? ORDER BY received DESC LIMIT 1",
                                  (feed, key)).fetchone()
                if last is None or last[0] != digest:
                    db.execute("INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?, ?)",
                               (feed, key, received, float(started), digest, gzip.compress(text.encode("utf-8"), mtime=0)))
                    changed = True
            failure = None if ok else str(error or "no content")[:400]
            db.execute("INSERT INTO polls VALUES (?, ?, ?, ?, ?, ?, ?)", (feed, key, float(started), received, int(ok), int(changed), failure))
            db.commit()
            row = stats.setdefault((feed, key), _empty_stats())
            row["polls"] += 1
            row["last_poll"] = received
            if ok:
                row["ok"] += 1
                row["first_ok"] = row["first_ok"] if row["first_ok"] is not None else received
                row["last_ok"] = row["last_good"] = received
                row["last_error"] = None
            else:
                row["last_error"] = failure
            row["snapshots"] += int(changed)
        return changed

    def _store_history(self, feed: str, key: str, rows: Sequence[tuple[float, Mapping[str, Any]]], *, fetched: float) -> int:
        """Keep settled history: each row under its own point-in-time stamp (a candle's close, a
        settlement's fundingTime), never the fetch time, which is kept as `started`; a stamp already
        held is never stored again, so the first version received stands. Returns how many were new."""
        if self._closed or not rows:
            return 0
        prepared = [(float(at), json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
                    for at, payload in rows]
        with self._lock:
            stats = self._load_stats()  # before these rows are written, or they would be counted twice
            db = self.db
            new: list[float] = []
            for at, text in prepared:
                cursor = db.execute("INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?, ?, ?)",
                                    (feed, key, at, float(fetched), hashlib.sha256(text.encode("utf-8")).hexdigest()[:32],
                                     gzip.compress(text.encode("utf-8"), mtime=0)))
                if cursor.rowcount:
                    new.append(at)
            row = self._history_row(feed, key, fetched)
            if new:
                low, high = min(new), max(new)
                row["oldest"] = low if row["oldest"] is None else min(float(row["oldest"]), low)
                row["newest"] = high if row["newest"] is None else max(float(row["newest"]), high)
                row["stored"] += len(new)
                counts = stats.setdefault((feed, key), _empty_stats())
                counts["snapshots"] += len(new)
                counts["first_ok"] = low if counts["first_ok"] is None else min(float(counts["first_ok"]), low)
                counts["last_ok"] = high if counts["last_ok"] is None else max(float(counts["last_ok"]), high)
            self._save_history(feed, key)  # commits the rows with it
        return len(new)

    def _note(self, feed: str, key: str, *, started: float, finished: float, ok: bool, changed: bool, error: str | None) -> None:
        """The `polls` row of one request for a history feed (a live poll or a backfill page), and its
        outcome on the key's `backfills` row."""
        if self._closed:
            return
        received = _received(finished)
        failure = None if ok else str(error or "no content")[:400]
        with self._lock:
            stats = self._load_stats()  # before this poll is written, or it would be counted twice
            self.db.execute("INSERT INTO polls VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (feed, key, float(started), received, int(ok), int(changed), failure))
            row = self._history_row(feed, key, started)
            row["updated"], row["error"] = received, failure
            self._save_history(feed, key)  # commits the poll with it
            counts = stats.setdefault((feed, key), _empty_stats())
            counts["polls"] += 1
            counts["last_poll"] = received
            if ok:
                counts["ok"] += 1
                counts["last_good"] = received
                counts["last_error"] = None
            else:
                counts["last_error"] = failure

    def _load_stats(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Per (feed, key) counters, read from the store once and kept current by `record`,
        `_store_history` and `_note` (health is written every tick, and a GROUP BY over every poll
        ever is not a tick's work). `first_ok` and `last_ok` are the first and last successful polls
        of a live feed, and the oldest and newest rows held of a history feed; `last_good` is the
        last successful poll of either."""
        with self._lock:
            if self._stats is None:
                stats: dict[tuple[str, str], dict[str, Any]] = {}
                for feed, key, first_ok, last_ok, last_poll, polls, oks in self.db.execute(
                        "SELECT feed, key, MIN(CASE WHEN ok = 1 THEN finished END), MAX(CASE WHEN ok = 1 THEN finished END), "
                        "MAX(finished), COUNT(*), SUM(ok) FROM polls GROUP BY feed, key"):
                    history = feed in HISTORY_FEEDS
                    stats[(feed, key)] = {**_empty_stats(), "first_ok": None if history else first_ok,
                                          "last_ok": None if history else last_ok, "last_good": last_ok,
                                          "last_poll": last_poll, "polls": int(polls or 0), "ok": int(oks or 0)}
                for feed, key, count, oldest, newest in self.db.execute(
                        "SELECT feed, key, COUNT(*), MIN(received), MAX(received) FROM snapshots GROUP BY feed, key"):
                    row = stats.setdefault((feed, key), _empty_stats())
                    row["snapshots"] = int(count)
                    if feed in HISTORY_FEEDS:
                        row["first_ok"], row["last_ok"] = oldest, newest
                for (feed, key), row in stats.items():
                    if row["last_poll"] is not None and row["last_poll"] != row["last_good"]:
                        found = self.db.execute("SELECT error FROM polls WHERE feed = ? AND key = ? ORDER BY finished DESC LIMIT 1",
                                                (feed, key)).fetchone()
                        row["last_error"] = found[0] if found else None
                self._stats = stats
            return self._stats

    @staticmethod
    def _row(received: float, blob: bytes) -> dict[str, Any]:
        return {**json.loads(gzip.decompress(blob).decode("utf-8")), "t": stamp(received)}

    def _history_view(self, feed: str, key: str, start: float, end: float) -> list[tuple[float, dict[str, Any]]]:
        """A history feed's rows as a strategy sees them: the row held last at or before `start`
        (if any) and every row in (start, end], oldest first, each with the fields `_vol_rows` or
        `_funding_rows` derive from the rows at or before it (read back `LOOKBACK_DAYS` for them)."""
        db = self.db
        opening = db.execute("SELECT received FROM snapshots WHERE feed = ? AND key = ? AND received <= ? "
                             "ORDER BY received DESC LIMIT 1", (feed, key, start)).fetchone()
        first = float(opening[0]) if opening else float(start)
        rows = [(float(at), json.loads(gzip.decompress(blob).decode("utf-8"))) for at, blob in db.execute(
            "SELECT received, payload FROM snapshots WHERE feed = ? AND key = ? AND received >= ? AND received <= ? ORDER BY received",
            (feed, key, first - LOOKBACK_DAYS.get(feed, 0) * 86400.0, end))]
        if not rows:
            return []
        with self._lock:
            since = (self._load_stats().get((feed, key)) or {}).get("first_ok")
        if feed in RECORDERS:
            derived = RECORDERS[feed].derive(rows, since)
        else:
            derived = _vol_rows(rows) if feed == "vol" else _funding_rows(rows, since)
        return [(at, row) for at, row in derived if at >= first]

    # -- reads -----------------------------------------------------------------------------------
    def latest(self, wanted: Any, now: Any) -> dict[str, dict[str, dict[str, Any]]]:
        """What a live wake is handed: for each declared key the last row stamped at or before
        `now` (`sports`, `perps`: received; `vol`, `funding`: final), stamped `t`. A key with
        nothing held is absent."""
        now_ts = _epoch(now)
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for feed, keys in requested(wanted).items():
            for key in keys:
                if feed in HISTORY_FEEDS:
                    view = self._history_view(feed, key, now_ts, now_ts)
                    if view:
                        out.setdefault(feed, {})[key] = {**view[-1][1], "t": stamp(view[-1][0])}
                    continue
                row = self.db.execute("SELECT received, payload FROM snapshots WHERE feed = ? AND key = ? AND received <= ? "
                                      "ORDER BY received DESC LIMIT 1", (feed, key, now_ts)).fetchone()
                if row is not None:
                    out.setdefault(feed, {})[key] = self._row(row[0], row[1])
        return out

    def series(self, wanted: Any, start: Any, end: Any, step_seconds: float, *,
               max_bytes: int = TAPE_BYTES) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """The rows a replay tape carries over [start, end], by feed and key, oldest first, each
        stamped `t` (when it was received, or for `vol` and `funding` when it became final). Only
        rows stamped at or before `end`; the row stamped last at or before `start` opens each series,
        so the first step sees what a wake would have. At most one row a step (`_thin`), and a key
        whose rows would take more than its share of `max_bytes` is sampled at twice the step until
        it fits: a coarser view of the past, never a look at the future. The replay shows a row only
        from its `t` on."""
        plan = requested(wanted)
        start_ts, end_ts = _epoch(start), _epoch(end)
        step = max(1.0, float(step_seconds or 300))
        keys = [(feed, key) for feed, rows in plan.items() for key in rows]
        share = max(1.0, float(max_bytes)) / max(1, len(keys))
        out: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for feed, key in keys:
            if feed in HISTORY_FEEDS:
                view = self._history_view(feed, key, start_ts, end_ts)
                if not view:
                    continue
                times = [at for at, _ in view]
                opened = times[0] <= start_ts
                texts = {i: json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for i, (_, row) in enumerate(view)}
                blobs: list[bytes] = []  # every text is already made
            else:
                opening = self.db.execute("SELECT received, payload FROM snapshots WHERE feed = ? AND key = ? AND received <= ? "
                                          "ORDER BY received DESC LIMIT 1", (feed, key, start_ts)).fetchall()
                rows = opening + self.db.execute("SELECT received, payload FROM snapshots WHERE feed = ? AND key = ? AND received > ? "
                                                 "AND received <= ? ORDER BY received", (feed, key, start_ts, end_ts)).fetchall()
                if not rows:
                    continue
                times = [row[0] for row in rows]
                opened = bool(opening)
                texts = {}
                blobs = [row[1] for row in rows]

            def text(index: int, texts: dict[int, str] = texts, blobs: list[bytes] = blobs) -> str:
                if index not in texts:
                    texts[index] = gzip.decompress(blobs[index]).decode("utf-8")
                return texts[index]

            width = step
            while True:
                picked = _thin(times, width, keep_first=opened)
                if len(picked) <= 1 or sum(len(text(i)) + 40 for i in picked) <= share:
                    break
                width *= 2
            out.setdefault(feed, {})[key] = [{**json.loads(text(i)), "t": stamp(times[i])} for i in picked]
        return out

    def coverage(self, wanted: Any = None, start: Any = None, end: Any = None) -> dict[str, dict[str, dict[str, Any]]]:
        """Per feed and key: whether the House polls it, when recording began and its last, the
        counts, and -- over [start, end] when both are given -- the seconds covered. For `sports` and
        `perps` `first_ok`/`last_ok` are the first and last successful polls, and each successful
        poll covers until the next, for at most the feed's `GAP_SECONDS`. For `vol` and `funding` they
        are the oldest and newest rows held, each ROW covers until the next (at most `GAP_SECONDS`),
        so the backfilled span counts as covered -- it is point-in-time history -- and `backfill` says
        where it came from and how far it has come."""
        plan = requested(wanted) if wanted is not None else {feed: self.keys(feed) for feed in FEEDS if self.keys(feed)}
        window = (_epoch(start), _epoch(end)) if start is not None and end is not None else None
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for feed, keys in plan.items():
            polled = set(self.keys(feed))
            for key in keys:
                with self._lock:
                    row = dict(self._load_stats().get((feed, key)) or _empty_stats())
                entry: dict[str, Any] = {
                    "polled": key in polled,
                    "first_ok": stamp(row["first_ok"]) if row["first_ok"] is not None else None,
                    "last_ok": stamp(row["last_ok"]) if row["last_ok"] is not None else None,
                    "polls": row["polls"], "ok": row["ok"], "snapshots": row["snapshots"], "last_error": row["last_error"],
                }
                if feed in HISTORY_FEEDS:
                    entry["backfill"] = self._provenance(feed, key, polled=key in polled)
                if window is not None:
                    entry["window"] = [stamp(window[0]), stamp(window[1])]
                    entry["covered_seconds"] = round(self._covered_seconds(feed, key, *window), 3) if row["first_ok"] is not None else 0.0
                out.setdefault(feed, {})[key] = entry
        return out

    def _covered_seconds(self, feed: str, key: str, start: float, end: float) -> float:
        gap = float(GAP_SECONDS.get(feed, SPORTS_QUIET_SECONDS))
        if feed in RECORDERS and RECORDERS[feed].sparse:
            return self._searched_seconds(feed, key, start, end, gap)
        if feed in HISTORY_FEEDS:  # the rows themselves, backfilled or polled: point-in-time history
            query = ("SELECT received FROM snapshots WHERE feed = ? AND key = ? AND received > ? AND received <= ? "
                     "ORDER BY received")
        else:
            query = ("SELECT finished FROM polls WHERE feed = ? AND key = ? AND ok = 1 AND finished > ? AND finished <= ? "
                     "ORDER BY finished")
        times = [t for (t,) in self.db.execute(query, (feed, key, start - gap, end))]
        covered = 0.0
        for index, at in enumerate(times):
            upto = min(times[index + 1] if index + 1 < len(times) else end, at + gap, end)
            since = max(at, start)
            if upto > since:
                covered += upto - since
        return covered

    def _provenance(self, feed: str, key: str, *, polled: bool) -> dict[str, Any]:
        """Where a history key's rows came from and how far its backfill has come, from `backfills`.
        `pending`: polled here and still short of its target -- a replay that needs it waits."""
        with self._lock:
            row = dict(self._history_state().get((feed, key)) or {})
        unlisted = self._unlisted_now(feed, key, self.clock())
        if not row:
            return {"source": _source(feed, key), "since": None, "until": None, "rows": 0, "pages": 0, "complete": False,
                    "exhausted": False, "pending": polled}
        out = {"source": row["source"], "target": stamp(row["target"]), "began": stamp(row["began"]),
               "since": stamp(row["oldest"]) if row["oldest"] is not None else None,
               "until": stamp(row["newest"]) if row["newest"] is not None else None,
               "rows": row["stored"], "pages": row["pages"], "complete": bool(row["done"]), "exhausted": bool(row["exhausted"]),
               "pending": polled and not row["done"] and not unlisted}
        if row["error"]:
            out["error"] = str(row["error"])[:200]
        return out

    # -- what the House says about it ------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        """What `House.research_capabilities` announces: what is recorded, since when, how often, and
        what a replay of a strategy that reads it needs -- for `vol` and `funding` also since when the
        backfilled history reaches and whether a replay can use it now."""
        from .constitution import CONSTITUTION

        need = int(CONSTITUTION["ladder"]["replay"]["min_blocks"])
        now = self.clock()
        with self._lock:
            stats = {k: dict(v) for k, v in self._load_stats().items()}
        out: dict[str, Any] = {}
        for feed in FEEDS:
            keys = self.keys(feed)
            rows = {key: stats.get((feed, key)) or _empty_stats() for key in keys}
            firsts = [row["first_ok"] for row in rows.values() if row["first_ok"] is not None]
            out[feed] = {
                "what": WHAT[feed], "source": SOURCES[feed], "cadence": CADENCE[feed], "keys": keys,
                "recording": [key for key, row in rows.items() if row["first_ok"] is not None],
                "recording_since": stamp(min(firsts)) if firsts else None,
                "hours_recorded": round((now - min(firsts)) / 3600.0, 1) if firsts else 0.0,
                # The earliest a replay could accept a strategy declaring this feed, if recording is
                # never interrupted (a gap in recording pushes it later; `replay_coverage` measures it).
                "replay_possible_from": {"hour": stamp(min(firsts) + need * 3600.0), "day": stamp(min(firsts) + need * 86400.0)}
                                        if firsts else None,
                "failing_now": [key for key, row in rows.items() if row["last_error"]],
            }
            if feed in RECORDERS:
                out[feed]["host"] = RECORDERS[feed].host
                out[feed]["recorded"] = "at its final time (point-in-time history)" if feed in HISTORY_FEEDS else "live, at the House's receive time"
                waiting = self.waiting_for(feed)
                if waiting:
                    out[feed]["waiting_for"] = waiting
                if feed not in HISTORY_FEEDS:
                    out[feed]["point_in_time"] = POINT_IN_TIME[feed]
            if feed in HISTORY_FEEDS:
                provenance = {key: self._provenance(feed, key, polled=True) for key in keys}
                replayable: dict[str, list[str]] = {"hour": [], "day": []}
                windows = self._windows()
                for key in keys:
                    if rows[key]["first_ok"] is None:
                        continue
                    for horizon, block in (("hour", 3600.0), ("day", 86400.0)):
                        spans = [seconds for (_, h), seconds in windows.items() if h == horizon] or [BACKFILL_DAYS * 86400.0]
                        if all(self._covered_seconds(feed, key, now - span, now) >= need * block for span in spans):
                            replayable[horizon].append(key)
                out[feed].update({
                    "point_in_time": POINT_IN_TIME[feed],
                    "backfilled_since": {key: p["since"] for key, p in provenance.items() if p["since"]},
                    "backfill_complete": [key for key, p in provenance.items() if p["complete"]],
                    "backfill_in_progress": [key for key, p in provenance.items() if p["pending"]],
                    # Keys whose held rows cover the replay gate's blocks in every live window the House
                    # replays that horizon over (Alpaca's and Kalshi's): a strategy reading them replays now.
                    "replayable_now": replayable,
                })
        out["sports"]["unmapped_series"] = self.unmapped()[:40]
        if "weather" in out:
            out["weather"]["unmapped_series"] = weather_unmapped(self.niches())[:40]
        out["request"] = ("NEEDS['feeds'] = {'sports': ['nfl', 'mlb'], 'perps': ['BTC', 'ETH'], 'vol': ['BTC'], 'funding': ['BTC', 'SOL'], "
                          "'weather': ['KXHIGHNY'], 'forecast': ['KNYC'], 'nws': ['KNYC'], 'earnings': ['AAPL'], "
                          "'earnings_date': ['AAPL'], 'rates': ['SOFR'], 'treasury': ['10Y'], 'odds': ['nfl'], 'tsa': ['checkpoint'], "
                          "'oi': ['BTC']} (known names only, at most six keys each; a Kalshi series names its league or its "
                          "settlement station) adds ctx['feeds'][feed][key]: the latest row stamped at or before now -- a live "
                          "feed's with when the House received it, a history feed's with when it became final (a candle's close, a "
                          "rate's settlement, an 8-K's acceptance, a forecast's issue plus its publication allowance). A key that is "
                          "absent is unavailable; a strategy must also work when ctx['feeds'] is absent.")
        live = ", ".join(feed for feed in FEEDS if feed not in HISTORY_FEEDS)
        history = ", ".join(HISTORY_FEEDS)
        out["replay"] = (f"Rows are replayed point in time by t. The live feeds ({live}) are recorded as received and nothing before "
                         f"recording began exists: a strategy that declares them is replayed only once every declared key has {need} "
                         f"blocks of its horizon recorded ({need} hours for an hour strategy, {need} days for a day strategy), and until "
                         f"then its replay is refused as unsupported input, which is not a trial. The history feeds ({history}) are "
                         "point-in-time history, backfilled from the sources' own history over the replay window and stamped when each "
                         "value became final, so a strategy that declares them is replayed at once (see replayable_now). Live wakes "
                         "are handed every feed at once.")
        return out

    def health(self) -> dict[str, Any]:
        """health.json's `feeds` block. Written at the end of every tick, so it never raises."""
        try:
            with self._lock:
                stats = {k: dict(v) for k, v in self._load_stats().items()}
                upcoming = dict(self._next)
                venues = dict(self._venues)
                hot = dict(self._hot)
            out: dict[str, Any] = {}
            for feed in FEEDS:
                keys = self.keys(feed)
                rows = {key: stats.get((feed, key)) or _empty_stats() for key in keys}
                firsts = [row["first_ok"] for row in rows.values() if row["first_ok"] is not None]
                lasts = [row["last_ok"] for row in rows.values() if row["last_ok"] is not None]
                due = [at for (name, _), at in upcoming.items() if name == feed]
                out[feed] = {"keys": len(keys), "recording": len(firsts),
                             "since": stamp(min(firsts)) if firsts else None, "last_ok": stamp(max(lasts)) if lasts else None,
                             "failing": sorted(key for key, row in rows.items() if row["last_error"])[:20],
                             "polls": sum(row["polls"] for row in rows.values()),
                             "snapshots": sum(row["snapshots"] for row in rows.values()),
                             "next_due": stamp(min(due)) if due else None}
                if feed in RECORDERS:
                    out[feed]["host"] = RECORDERS[feed].host
                    waiting = self.waiting_for(feed)
                    if waiting:
                        out[feed]["waiting_for"] = waiting
                if feed in HISTORY_FEEDS:
                    provenance = {key: self._provenance(feed, key, polled=True) for key in keys}
                    out[feed]["backfill"] = {"complete": sum(1 for p in provenance.values() if p["complete"]),
                                             "in_progress": sorted(key for key, p in provenance.items() if p["pending"])[:20],
                                             "unlisted": sorted(key for key in keys if self._unlisted_now(feed, key, self.clock()))}
            out["sports"]["live_boards"] = sorted(league for league, live in hot.items() if live)
            out["sports"]["unmapped_series"] = len(self.unmapped())
            out["perps"]["venues_answering"] = venues
            backfill_due = upcoming.get(("backfill", "*"))
            out["backfill_next_due"] = stamp(backfill_due) if backfill_due is not None and self._backfill_pending() else None
            out["store_mb"] = round(self.path.stat().st_size / 1e6, 2) if self.path.exists() else 0.0
            return out
        except Exception as exc:  # noqa: BLE001 - a report must not stop the tick that writes it
            return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    # -- after a pass ----------------------------------------------------------------------------
    def _warn(self, feed: str, text: str) -> None:
        """A warning, at most one an hour a feed. Never an error (see `ALERT_SECONDS`)."""
        now = self.clock()
        with self._lock:
            if now - self._warned.get(feed, float("-inf")) < ALERT_SECONDS:
                return
            self._warned[feed] = now
        try:
            if self._alert is not None:
                self._alert("warning", text)
        except Exception:  # noqa: BLE001 - the ledger may already be closed on the way out
            pass

    def _after_pass(self, out: Mapping[str, Any]) -> None:
        failed: dict[str, list[tuple[str, str]]] = {}
        for feed, key, error in out.get("failed") or []:
            failed.setdefault(feed, []).append((key, error))
        for feed, rows in failed.items():
            polled = len(self.keys(feed))
            by_key = dict(rows)  # a key whose live poll and backfill page both failed is one key
            sample = "; ".join(f"{key}: {error[:120]}" for key, error in list(by_key.items())[:3])
            self._warn(feed, f"feeds: {len(by_key)} of {polled} {feed} polls failed ({sample})")
        with self._lock:
            venues = dict(self._venues)
        silent = [venue for venue, answered in venues.items() if answered == 0]
        if "perps" in out.get("polled", []) and venues and silent and len(silent) < len(venues):
            self._warn("perps", f"feeds: {', '.join(silent)} answered for no coin this pass; the perps rows carry None for "
                                f"{'it' if len(silent) == 1 else 'them'}")
        self._publish_coverage()

    def _publish_coverage(self) -> None:
        """A `data.coverage` ledger row per feed, at most one per clock hour (as the options history's
        rows, `asset` says what it is). The store is the record; the ledger row is the index."""
        if self.ledger is None:
            return
        now = self.clock()
        hour = int(now // COVERAGE_SECONDS)
        for feed in FEEDS:
            if self._covered.get(feed) == hour:
                continue
            keys = self.keys(feed)
            if not keys:
                continue
            with self._lock:
                rows = {key: dict(self._load_stats().get((feed, key)) or _empty_stats()) for key in keys}
            firsts = [row["first_ok"] for row in rows.values() if row["first_ok"] is not None]
            lasts = [row["last_ok"] for row in rows.values() if row["last_ok"] is not None]
            failing = [key for key, row in rows.items() if row["last_error"]]
            provenance = {key: self._provenance(feed, key, polled=True) for key in keys} if feed in HISTORY_FEEDS else {}
            filling = [key for key, p in provenance.items() if p["pending"]]
            payload: dict[str, Any] = {
                "asset": "feed", "feed": feed, "source": SOURCES[feed], "cadence": CADENCE[feed],
                **({"host": RECORDERS[feed].host} if feed in RECORDERS else {}),
                "status": "unavailable" if not firsts else "partial" if failing or filling else "current",
                "start": stamp(min(firsts)) if firsts else None, "end": stamp(max(lasts)) if lasts else None,
                "keys": {key: {"first": stamp(row["first_ok"]) if row["first_ok"] is not None else None,
                               "last": stamp(row["last_ok"]) if row["last_ok"] is not None else None,
                               "polls": row["polls"], "ok": row["ok"], "snapshots": row["snapshots"],
                               **({"error": str(row["last_error"])[:160]} if row["last_error"] else {})}
                         for key, row in rows.items()},
                "point_in_time": POINT_IN_TIME[feed],
                "recorded_at": stamp(now),
            }
            if feed == "sports":
                payload["unmapped_series"] = self.unmapped()[:60]
            if provenance:
                payload["backfill"] = {key: {k: p.get(k) for k in ("source", "since", "until", "rows", "complete", "exhausted")}
                                       for key, p in provenance.items()}
            ident = f"data.coverage:feed:{feed}:{hour}"
            try:
                if self.ledger.get(ident) is None:
                    self.ledger.append("data.coverage", payload, id=ident)
                self._covered[feed] = hour
            except Exception:  # noqa: BLE001 - the store is the record; the ledger row is the index
                pass

    # -- the tool-request queue ------------------------------------------------------------------
    def fulfil_requests(self, commons: Any) -> list[str]:
        """Mark the open and blocked tool requests that plainly ask for a feed the House now records
        (`request_feed`) as fulfilled, so the research of the lines that asked wakes (the research
        gate counts a `tool.fulfilled` for its line). A feed with nothing recorded has not shipped.
        Idempotent: a fulfilled request is neither open nor blocked any more."""
        with self._lock:
            shipped = {feed for (feed, _), row in self._load_stats().items() if row.get("first_ok") is not None}
        if not shipped:
            return []
        done: list[str] = []
        for row in list(commons.open_requests(stale_days=0)) + list(commons.blocked_requests()):
            feed = request_feed(row.get("name"))
            if feed in shipped and str(row["id"]) not in done:
                commons.fulfil(str(row["id"]), self._outcome(feed), change="league/feeds.py")
                done.append(str(row["id"]))
        return done

    def _outcome(self, feed: str) -> str:
        from .constitution import CONSTITUTION

        need = int(CONSTITUTION["ladder"]["replay"]["min_blocks"])
        if feed in RECORDERS:
            return RECORDERS[feed].outcome(self, need)
        described = self.describe()[feed]
        since = described["recording_since"]
        keys = ", ".join(described["recording"]) or "none yet"
        if feed == "sports":
            head = (f"Shipped (league/feeds.py): the House records ESPN scoreboards -- status, score, period, clock, start and the "
                    f"sportsbook line of every game on the board -- for {keys}, {CADENCE['sports']}, since {since}. Declare "
                    "NEEDS['feeds'] = {'sports': ['nfl', ...]} (at most six; a Kalshi series such as KXNFLGAME names its league) "
                    "and read ctx['feeds']['sports'][league]. Line-ups, injuries and player props are not supplied.")
        elif feed == "perps":
            head = (f"Shipped (league/feeds.py): the House records perpetual funding and open interest (OKX, Hyperliquid, Kraken), "
                    f"Deribit DVOL (BTC, ETH) and the OKX funding z-score for {keys}, {CADENCE['perps']}, since {since}. Declare "
                    "NEEDS['feeds'] = {'perps': ['BTC', ...]} (at most six) and read ctx['feeds']['perps'][coin].")
        elif feed == "vol":
            return (f"Shipped (league/feeds.py): the House holds Deribit's DVOL (30-day implied volatility, annualized percent) "
                    f"for {keys} as hourly candles stamped at their close, backfilled from {since} and polled hourly. Declare "
                    "NEEDS['feeds'] = {'vol': ['BTC', 'ETH']} and read ctx['feeds']['vol'][coin]: open, high, low, close, "
                    "change_24h. Each row carries t, when the candle closed; a replay shows it from then on, and because the "
                    "history is backfilled a strategy that declares it is replayed at once.")
        else:
            return (f"Shipped (league/feeds.py): the House holds OKX's settled perpetual funding for {keys}, a row per "
                    f"settlement stamped at its fundingTime, backfilled from {since} and polled every 30 minutes. Declare "
                    "NEEDS['feeds'] = {'funding': ['BTC', ...]} (at most six) and read ctx['feeds']['funding'][coin]: rate, "
                    "interval_hours, avg_24h, avg_7d, zscore_30d (from rates settled at or before it). A replay shows each row "
                    "from its t on, and because the history is backfilled a strategy that declares it is replayed at once.")
        return (head + " Each row carries t, when the House received it; an absent key is unavailable. A replay shows the rows "
                f"point in time and accepts a strategy that declares them once {need} blocks of its horizon are recorded.")


# ------------------------------------------------------------------ the recorders of Sept 24, 2026
#: A source's answer for a key whose newest content it has confirmed is still current without
#: fetching it again (the weather ensemble, when no newer model run exists): a successful poll.
UNCHANGED = object()
#: How a recorder of Sept 24, 2026 says a key does not exist at its source (a ticker with no EDGAR
#: filer, a coin OKX does not list): not a failure, and asked again after `UNLISTED_SECONDS`.
NOT_LISTED = "not listed:"
#: How often the House's `.env` and the allowlist the repository records are read again.
ENV_SECONDS = 300.0
REPO_ROOT = Path(__file__).resolve().parents[1]
#: How often the weather ensemble asks Open-Meteo whether a newer model run exists.
RUN_CHECK_SECONDS = 900.0
_WEATHER_SERIES = re.compile(r"^KX(?:HIGH|LOW|RAIN|SNOW)[A-Z]*$")


def _unlisted(error: Any) -> bool:
    """Does a poll's error say the key does not exist at its source (not that the source failed)?"""
    text = str(error or "")
    return UNLISTED in text or NOT_LISTED in text


def _cadence(feed: str) -> tuple[float, float]:
    """(every, offset) of a history feed's passes (`_aligned`)."""
    if feed in RECORDERS:
        return float(RECORDERS[feed].every), float(RECORDERS[feed].offset)
    return float(VOL_SECONDS if feed == "vol" else FUNDING_SECONDS), float(HISTORY_OFFSET)


def league_hosts() -> tuple[str, ...]:
    """The hosts the repository records on the House box's egress allowlist: `LEAGUE_HOSTS` in
    `scripts/floor_box.py`, read with `ast` -- the deploy tool is never imported into the House. The
    owner's `floor_box.py hosts --add` widens the live list; the tuple is its record."""
    import ast

    try:
        tree = ast.parse((REPO_ROOT / "scripts" / "floor_box.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return ()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LEAGUE_HOSTS" for t in node.targets):
            try:
                return tuple(str(host).strip().lower() for host in ast.literal_eval(node.value))
            except (ValueError, TypeError):
                return ()
    return ()


def weather_stations(niches: Mapping[str, Any]) -> list[str]:
    """The settlement stations of the Kalshi weather series the desks trade (the weather desk's
    live and listed series first, then any other desk's), one each, in the order found."""
    from ltcm.data.weather import city_for_series

    out: list[str] = []
    for niche in niches.values():
        if getattr(niche, "venue", "") != "kalshi" or getattr(niche, "dormant", False):
            continue
        for series in getattr(niche, "universe", ()):
            if not _WEATHER_SERIES.match(str(series).upper()):
                continue
            city = city_for_series(series)
            if city is not None and city.station not in out:
                out.append(city.station)
    return out


def weather_unmapped(niches: Mapping[str, Any]) -> list[str]:
    """The weather series the desks trade that name no settlement station here (`KXRAIN`, a city
    Kalshi added after `ltcm/data/weather.py`'s table): reported, never guessed."""
    from ltcm.data.weather import city_for_series

    out: list[str] = []
    for niche in niches.values():
        if getattr(niche, "venue", "") != "kalshi" or getattr(niche, "dormant", False):
            continue
        for series in getattr(niche, "universe", ()):
            if _WEATHER_SERIES.match(str(series).upper()) and city_for_series(series) is None and series not in out:
                out.append(series)
    return out


def _words(name: Any) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_").split("_")) - {""}


class Source:
    """One recorder of Sept 24, 2026 (docs/goals/LTCM_CLOSE_THE_GAPS.md, workstream I, gap 7): a feed
    a strategy names in `NEEDS["feeds"]`, the host it reads, and how it is polled and stamped.

    A live source (`history` False) keeps what a poll returned under the House's receive time and is
    never backfilled: `poll(fetcher, keys, recorder, now)` answers each key's payload, `UNCHANGED`, or
    the exception that made its poll fail. A history source keeps rows under the moment the SOURCE
    says each became final -- an 8-K's acceptance, an interval's end, a forecast's issue plus its
    publication allowance -- and is backfilled over the replay window: `page(...)` answers one
    request of them, as `FeedRecorder._page` does for `vol` and `funding`. `sparse` history is a
    list of events (8-Ks): its coverage is the span its listing has been searched, not how dense its
    rows are. `env` names an owner's key the source needs: without it (and its host on the allowlist
    the repository records) it polls nothing and says it is waiting, never that it failed."""

    name = ""
    host = ""
    what = ""
    source = ""
    cadence = ""
    point_in_time = ""
    history = False
    sparse = False
    #: One request answers every key (a page of par yields, a table of rates) instead of one a key.
    batch = False
    every = 3600.0
    offset = 0.0
    #: Coverage: how long one good poll (a live source) or one row (a history source) counts.
    gap = 3 * 3600.0
    lookback_days = 0
    #: How far back a history source is backfilled, in days; None: the House's replay window.
    backfill_days: float | None = None
    env: str | None = None
    #: The most keys the House polls (what one strategy may DECLARE is `MAX_KEYS`).
    max_keys = 64
    timeout = TIMEOUT
    #: A key a strategy might write, for the texts that say how to declare it.
    example = ""
    #: What a strategy reads beside each row, said once in the tool-request answer.
    note = ""

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        return []

    def key_of(self, raw: Any) -> str | None:
        return None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        raise NotImplementedError

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: "FeedRecorder", now: float) -> Mapping[str, Any]:
        raise NotImplementedError

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: "FeedRecorder") -> dict[str, Any]:
        raise NotImplementedError

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        """The fields a strategy reads beside each history row, from rows stamped at or before it."""
        return [(at, dict(payload)) for at, payload in rows]

    def endpoint(self, key: str) -> str:
        return self.source

    def redact(self, text: str, recorder: "FeedRecorder") -> str:
        """An error with the owner's key taken out: a transport error names the whole URL, and a
        keyed source's key rides in its query."""
        if self.env:
            secret = recorder.owner_key(self.env)
            if secret:
                text = text.replace(secret, "***")
        return text

    def asks(self, words: set[str]) -> bool:
        """Does a tool request whose name has these words plainly ask for this feed?"""
        return False

    def outcome(self, recorder: "FeedRecorder", need: int) -> str:
        """The answer a fulfilled tool request carries: what is recorded, how to declare and read it."""
        described = recorder.describe().get(self.name) or {}
        keys = ", ".join(described.get("recording") or []) or "none yet"
        since = described.get("recording_since")
        head = (f"Shipped (league/feeds.py): the House records {self.what}, for {keys}, {self.cadence}, since {since}. Declare "
                f"NEEDS['feeds'] = {{'{self.name}': ['{self.example}']}} (at most six keys) and read "
                f"ctx['feeds']['{self.name}'][key]. {self.note}".rstrip() + " ")
        if self.history:
            return head + ("Each row carries t, when it became final; a replay shows it from then on, and because the history is "
                           "backfilled from the source's own record a strategy that declares it is replayed at once.")
        return head + ("Each row carries t, when the House received it; an absent key is unavailable. A replay shows the rows point "
                       f"in time and accepts a strategy that declares them once {need} blocks of its horizon are recorded.")


class WeatherEnsemble(Source):
    """Open-Meteo's GFS and ECMWF ensembles: the fair value of a Kalshi temperature bracket is the
    share of members that land in it, and the weather desk is the one family with a proven real
    record (Sept 24, 2026). Keyed by settlement station, polled only when a model has a newer run."""

    name = "weather"
    host = "ensemble-api.open-meteo.com"
    source = ("open-meteo: ensemble-api.open-meteo.com/v1/ensemble (GFS 31 and ECMWF 51 members, hourly) per settlement station, "
              "and each model run's start and availability from its meta.json")
    cadence = "the model runs are checked every 15 minutes, and a station is fetched again only when Open-Meteo has a newer run"
    what = ("per settlement station, the ensemble members' daily HIGH and LOW (F) and precipitation TOTAL (inches) for each of the "
            "next three whole NWS climate days (midnight to midnight local STANDARD time: the day the CLI report, and every Kalshi "
            "high, low and rain market, settles on), each {members, mean, sd, p10, p50, p90, min, max, n}, and runs: each model's "
            "run start (init) and when Open-Meteo had it (available)")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay; Open-Meteo "
                     "keeps no archive of its ensembles, so nothing is backfilled (the forecast feed is the backfilled history)")
    every = RUN_CHECK_SECONDS
    gap = 3 * 3600.0
    max_keys = 24
    timeout = 30.0
    example = "KXHIGHNY"
    note = ("dates[day] = {high, low, precip_in}, the day a CLI date; runs[model] = {model, init, available, modified}. The "
            "share of `members` inside a bracket is its ensemble probability (ltcm.data.openmeteo.bracket_probability rounds "
            "half-up as the NWS does); members are hourly samples at the nearest model cell, a little cooler than a station's "
            "maximum, which a strategy calibrates.")

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        return weather_stations(recorder.niches())

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.weather import station_for

        return station_for(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.openmeteo import OpenMeteo

        return OpenMeteo(transport, timeout=self.timeout, clock=clock)

    def runs(self, fetcher: Any, recorder: "FeedRecorder", now: float) -> dict[str, Any]:
        """The newest run of each ensemble model, asked at most every `RUN_CHECK_SECONDS`."""
        from ltcm.data.openmeteo import ENSEMBLE_HOST, ENSEMBLE_RUN_MODELS

        state = recorder.state(self.name)
        if state.get("runs") is None or now - float(state.get("checked") or 0.0) >= RUN_CHECK_SECONDS:
            state["runs"] = {name: fetcher.run(model, ENSEMBLE_HOST) for name, model in ENSEMBLE_RUN_MODELS.items()}
            state["checked"] = now
        return state["runs"]

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: "FeedRecorder", now: float) -> Mapping[str, Any]:
        from ltcm.data.weather import city_of_station, standard_offset_hours

        runs = self.runs(fetcher, recorder, now)
        seen = recorder.state(self.name).setdefault("seen", {})
        out: dict[str, Any] = {}
        for key in keys:
            if seen.get(key) == runs and not recorder.failing(self.name, key):
                out[key] = UNCHANGED  # its newest row came from these very runs
                continue
            try:
                city = city_of_station(key)
                data = fetcher.ensemble_days(city.latitude, city.longitude, standard_offset_hours(city))
                out[key] = {"station": key, "city": city.name, "unit": "F", "precip_unit": "in", "runs": runs,
                            "dates": {row["date"]: {name: row[name] for name in ("high", "low", "precip_in")} for row in data["days"][:3]}}
                seen[key] = runs
            except Exception as exc:  # noqa: BLE001 - one station that fails is a failed poll of that station
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        if words & {"history", "historical", "archive", "archived", "backfill", "observation", "observations", "observed"}:
            return False
        return bool(words & {"ensemble", "ensembles", "gefs", "ecmwf", "openmeteo"}) or (
            bool(words & {"weather", "temperature", "temperatures"}) and bool(words & {"forecast", "forecasts", "model", "models"}))


class NwsForecast(Source):
    """The National Weather Service's own forecast for each settlement station, as issued: the NWS is
    also the authority whose CLI report the markets settle on."""

    name = "nws"
    host = "api.weather.gov"
    source = "nws: api.weather.gov /points/<lat,lon> -> /gridpoints/<office>/<x,y>/forecast and /forecast/hourly, per settlement station"
    cadence = "hourly per station"
    what = ("per settlement station, the National Weather Service forecast as issued: issued (its own updateTime), its 12-hour "
            "periods (name, start, end, daytime, temperature F, pop %, short) and, for the next climate days, the hourly forecast's "
            "max and min with the hours they cover")
    point_in_time = ("each row is stamped with the House's receive time -- never before the issued time it carries -- and shown "
                     "only from then on, live and in replay; the NWS keeps no archive of its forecasts, so nothing is backfilled")
    every = 3600.0
    gap = 3 * 3600.0
    max_keys = 24
    timeout = 20.0
    example = "KNYC"
    note = ("A daytime period's temperature is the NWS high and a night period's its low; days[i] = {date, hourly_max, "
            "hourly_min, hours, pop_max} over the climate day (local standard time), with hours < 24 where the forecast "
            "does not cover the day whole.")

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        return weather_stations(recorder.niches())

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.weather import station_for

        return station_for(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.weather import Weather

        return Weather(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: "FeedRecorder", now: float) -> Mapping[str, Any]:
        from ltcm.data.weather import city_of_station

        out: dict[str, Any] = {}
        for key in keys:
            try:
                out[key] = {name: value for name, value in fetcher.issued(city_of_station(key)).items() if name != "source"}
            except Exception as exc:  # noqa: BLE001 - a station that fails is a failed poll of that station
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        return "nws" in words or {"national", "weather", "service"} <= words


class ForecastHistory(Source):
    """GFS's and ECMWF's deterministic forecasts at one, two and three days' lead, from Open-Meteo's
    archive of them: a history a replay can use at once, where the ensemble can only be recorded.

    The stamp is the whole of its honesty. Open-Meteo defines `<var>_previous_dayN` as the value
    "predicted N x 24 hours before valid time" (https://open-meteo.com/en/docs/previous-runs-api),
    so for climate day D at lead N every hourly value was predicted by D 23:00 local standard time
    minus N days. A row for day X carries today X at lead 1, X+1 at lead 2 and X+2 at lead 3, all
    predicted by X-1 23:00; it is stamped `ALLOWANCE_HOURS` later, X 11:00 local standard time, for
    the run to have been published (Sept 23, 2026: Open-Meteo had GFS 0.13's run 5.6 hours after it
    began, ECMWF IFS 0.25's 7.3). A live pass and the backfill stamp a row by the same rule, never
    with when it was fetched. Day 0 is never asked for: it is the first hours of each run,
    published after most of the hours it covers."""

    name = "forecast"
    host = "historical-forecast-api.open-meteo.com"
    source = ("open-meteo: historical-forecast-api.open-meteo.com/v1/forecast temperature_2m_previous_day1..3 and "
              "precipitation_previous_day1..3, models gfs_seamless and ecmwf_ifs025, per settlement station")
    cadence = "a row a station a day, stamped 11:00 local standard time and polled hourly; backfilled over the replay window"
    what = ("per settlement station, one row a day: GFS's and ECMWF's deterministic forecasts of the climate day's HIGH and LOW (F) "
            "and precipitation TOTAL (inches) -- today at one day's lead, tomorrow at two, the day after at three -- as dates: "
            "{day: {lead_days, models: {gfs_seamless: {high, low, precip_in}, ecmwf_ifs025: {...}}}}, with issued_by, the "
            "latest any of them can have been made")
    point_in_time = ("each row is stamped 11:00 local standard time: a lead-N value was predicted at most N days before its hour "
                     "(Open-Meteo's definition), so everything in the row was made by 23:00 the evening before, and the stamp adds "
                     "a 12-hour allowance for the run to be published (the runs of Sept 23 were published 5.6-7.3 hours after "
                     "they began); backfilled rows are stamped by the same rule, never with when they were fetched, and day 0 -- "
                     "forecasts published after the hours they cover -- is never used")
    history = True
    every = 3600.0
    offset = 150.0
    gap = 25 * 3600.0
    max_keys = 24
    timeout = 30.0
    example = "KNYC"
    note = ("dates[day] = {lead_days, models: {gfs_seamless: {high, low, precip_in}, ecmwf_ifs025: {...}}}; a model missing "
            "an hour of a day at a lead is absent for it.")
    ALLOWANCE_HOURS = 12
    #: Days of rows one request asks for (a month of hourly lead values: about 60 KB).
    PAGE_DAYS = 31

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        return weather_stations(recorder.niches())

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.weather import station_for

        return station_for(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.openmeteo import OpenMeteo

        return OpenMeteo(transport, timeout=self.timeout, clock=clock)

    def endpoint(self, key: str) -> str:
        return f"https://historical-forecast-api.open-meteo.com/v1/forecast?station={key}&hourly=<var>_previous_day1..3"

    def stamp_of(self, day: Any, offset_hours: float) -> float:
        """The row of climate day `day`: its local standard midnight, plus `ALLOWANCE_HOURS` - 1."""
        from datetime import date as date_type

        start = datetime.combine(day if isinstance(day, date_type) else date_type.fromisoformat(str(day)[:10]),
                                 datetime.min.time(), tzinfo=timezone.utc).timestamp() - float(offset_hours) * 3600.0
        return start + (self.ALLOWANCE_HOURS - 1) * 3600.0

    def day_at(self, moment: float, offset_hours: float) -> Any:
        """The newest day whose row is stamped at or before `moment`."""
        shifted = float(moment) + float(offset_hours) * 3600.0 - (self.ALLOWANCE_HOURS - 1) * 3600.0
        return datetime.fromtimestamp(math.floor(shifted / 86400.0) * 86400.0, timezone.utc).date()

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: "FeedRecorder") -> dict[str, Any]:
        """The rows of the days whose stamp lies in [floor, now] and before `before`, newest
        `PAGE_DAYS` of them, from one request: each day X's leads 1-3 need climate days X to X+2,
        which the UTC dates X to X+3 cover whole. A live pass (`before` None) that already holds
        the newest row that can exist asks nothing."""
        from datetime import timedelta

        from ltcm.data.weather import city_of_station, standard_offset_hours

        city = city_of_station(key)
        offset = standard_offset_hours(city)
        top = float(now) if before is None else min(float(now), float(before) - 0.001)
        last = self.day_at(top, offset)
        first = self.day_at(float(floor) - 0.001, offset) + timedelta(days=1)  # the first day stamped at or after floor
        if before is None:
            newest = (recorder._load_stats().get((self.name, key)) or {}).get("last_ok")
            if newest is not None:
                first = max(first, self.day_at(float(newest), offset) + timedelta(days=1))  # held already
        if last < first:
            return {"rows": [], "reached": True, "exhausted": False}
        start = max(first, last - timedelta(days=self.PAGE_DAYS - 1))
        answer = fetcher.previous_runs(city.latitude, city.longitude, start.isoformat(), (last + timedelta(days=3)).isoformat(), offset)
        days = answer.get("days") or {}
        rows = []
        day = start
        while day <= last:
            dates = {}
            for lead in (1, 2, 3):
                target = (day + timedelta(days=lead - 1)).isoformat()
                models = (days.get(target) or {}).get(lead)
                if models:
                    dates[target] = {"lead_days": lead, "models": models}
            stamp_at = self.stamp_of(day, offset)
            if dates and stamp_at <= now:
                rows.append((stamp_at, {"station": key, "city": city.name, "unit": "F", "precip_unit": "in",
                                        "issued_by": stamp(stamp_at - self.ALLOWANCE_HOURS * 3600.0),
                                        "allowance_hours": self.ALLOWANCE_HOURS, "dates": dates}))
            day += timedelta(days=1)
        reached = start <= first
        return {"rows": rows, "reached": reached, "exhausted": not rows and not reached}

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"forecast", "forecasts"}) and bool(words & {"history", "historical", "archive", "archived", "backfill",
                                                                         "lead", "leads", "previous"}) \
            and not words & {"observation", "observations", "observed", "actual", "actuals"}


#: The desks whose stocks report earnings (the brief's two), and the desk whose symbols are funds.
EARNINGS_DESKS = ("alpaca-megacaps", "alpaca-options")
FUND_DESKS = ("alpaca-index-etfs",)


def earnings_tickers(niches: Mapping[str, Any]) -> list[str]:
    """The stocks the megacap and options desks trade, funds (SPY, QQQ, IWM) left out: a fund files
    no earnings."""
    funds = {str(s).upper() for desk in FUND_DESKS if desk in niches for s in getattr(niches[desk], "universe", ())}
    out: list[str] = []
    for desk in EARNINGS_DESKS:
        niche = niches.get(desk)
        if niche is None or getattr(niche, "dormant", False):
            continue
        for symbol in getattr(niche, "universe", ()):
            symbol = str(symbol).upper()
            if symbol not in funds and "/" not in symbol and symbol not in out:
                out.append(symbol)
    return out


@lru_cache(maxsize=1)
def known_tickers() -> frozenset[str]:
    """Every stock a strategy may ask the earnings feeds for: those of the desks listed in niches.json."""
    from . import niches as niches_module

    return frozenset(earnings_tickers(niches_module.load()))


def _ticker_key(raw: Any) -> str | None:
    text = str(raw or "").strip().upper()
    return text if text in known_tickers() else None


_CALENDAR_WORDS = frozenset(("calendar", "calendars", "date", "dates", "upcoming", "forward", "next", "schedule", "scheduled",
                             "event", "events"))


def _earnings_words(words: set[str]) -> bool:
    """An earnings request the House can answer: times and dates, not the surprise (estimates
    against actuals), which it does not hold."""
    return "earnings" in words and not any(word.startswith("surp") for word in words) and not words & {"estimate", "estimates",
                                                                                                         "actuals", "panel"}


class EarningsHistory(Source):
    """Each earnings announcement of the stocks the equity desks trade, as EDGAR accepted it: the 8-K
    reporting Item 2.02 (results of operations), stamped at its acceptance time -- the source's own
    final timestamp, so the history is backfilled honestly. Full-text search (efts) answers a date
    only; the company browse feed on www.sec.gov carries the acceptance time (Sept 24, 2026)."""

    name = "earnings"
    host = "www.sec.gov"
    source = "sec: www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<ticker>&type=8-K&output=atom (each 8-K's items and acceptance time)"
    cadence = "every 10 minutes a stock (its newest 8-Ks); backfilled two years"
    what = ("per stock the alpaca-megacaps and alpaca-options desks trade, each earnings announcement the company filed -- the 8-K "
            "reporting Item 2.02, results of operations -- as {form, accession, filed, accepted, items, url, previous}: previous "
            "is the acceptance times of the four announcements before it, newest first")
    point_in_time = ("each row is stamped with EDGAR's acceptance time, the moment the filing became public, and shown only from "
                     "then on, live and in replay; the history is backfilled from EDGAR's listing and stamped the same way, never "
                     "with when it was fetched. The 8-K follows the company's press release by minutes, so a row can trail the news, "
                     "never lead it")
    history = True
    sparse = True
    every = 600.0
    gap = 3600.0
    lookback_days = 370
    backfill_days = 370
    max_keys = 32
    timeout = 30.0
    example = "AAPL"
    note = ("A stock with no row has had no announcement in the searched span, or files its results another way (a foreign "
            "issuer's 6-K is not recorded); the next date is the earnings_date feed.")
    #: Filings read a page, and pages a pass at most (320 8-Ks is years of any stock here).
    LISTING = 40
    MAX_LISTING_PAGES = 8

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        return earnings_tickers(recorder.niches())

    def key_of(self, raw: Any) -> str | None:
        return _ticker_key(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data import CONTACT_USER_AGENT, HttpTransport
        from ltcm.data.edgar import MIN_INTERVAL, Edgar

        return Edgar(transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL), timeout=self.timeout)

    def endpoint(self, key: str) -> str:
        return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={key}&type=8-K&output=atom"

    def page(self, fetcher: Any, key: str, *, before: float | None, floor: float, now: float, recorder: "FeedRecorder") -> dict[str, Any]:
        """The 2.02 filings accepted in [floor, now] (and before `before`), from the listing read
        newest first until a filing older than the floor: a live pass reads back to a day before its
        last good poll (EDGAR shows a filing moments after its acceptance), the backfill to its
        target. A listing longer than `MAX_LISTING_PAGES` fails the page -- it never claims a span it
        did not read -- and a ticker EDGAR does not know is `NOT_LISTED`."""
        from ltcm.data import DataError

        if before is None:
            last = (recorder._load_stats().get((self.name, key)) or {}).get("last_good")
            if last is not None:
                floor = max(float(floor), float(last) - 86400.0)
        rows: list[tuple[float, dict[str, Any]]] = []
        for number in range(self.MAX_LISTING_PAGES):
            try:
                answer = fetcher.filings(key, form="8-K", start=number * self.LISTING, count=self.LISTING)
            except DataError as exc:
                if "no company feed" in str(exc):
                    raise DataError(f"{NOT_LISTED} EDGAR knows no filer {key}") from exc
                raise
            for entry in answer["entries"]:
                at = _epoch(entry["accepted"])
                if at < floor:
                    return {"rows": rows, "reached": True, "exhausted": False}
                if at > now or (before is not None and at >= before):
                    continue
                if "2.02" in entry["items"] and str(entry.get("form") or "").startswith("8-K"):
                    rows.append((at, {"ticker": key, "cik": answer["cik"], "company": answer["company"], "form": entry["form"],
                                      "accession": entry["accession"], "filed": entry["filed"], "accepted": entry["accepted"],
                                      "items": entry["items"], "url": entry["url"]}))
            if len(answer["entries"]) < self.LISTING:
                return {"rows": rows, "reached": False, "exhausted": True}  # the listing ends: the filer's whole history read
        raise DataError(f"sec filings {key}: more than {self.MAX_LISTING_PAGES * self.LISTING} 8-Ks since {stamp(floor)}; "
                        "the span was not read to its end")

    def derive(self, rows: Sequence[tuple[float, Mapping[str, Any]]], since: float | None) -> list[tuple[float, dict[str, Any]]]:
        """Each announcement with `previous`: the acceptance times of the four before it, newest first."""
        out = []
        for index, (at, payload) in enumerate(rows):
            earlier = [stamp(prior) for prior, _ in rows[max(0, index - 4):index]]
            out.append((at, {**payload, "previous": earlier[::-1]}))
        return out

    def asks(self, words: set[str]) -> bool:
        # Not "time": every point_in_time_* request has it. A calendar is the next date (earnings_date).
        return _earnings_words(words) and not words & _CALENDAR_WORDS and bool(
            words & {"announcement", "announcements", "8k", "filing", "filings", "history", "historical", "edgar", "sec",
                     "released", "release", "acceptance", "accepted"})


class EarningsDate(Source):
    """The next earnings date of each stock the equity desks trade, as Nasdaq shows it now (the
    company's own date, or Zacks' estimate from its past dates). Nasdaq publishes no time a date
    first appeared, so a row is stamped when the House read it, and never backfilled."""

    name = "earnings_date"
    host = "api.nasdaq.com"
    source = "nasdaq: api.nasdaq.com/api/analyst/<SYMBOL>/earnings-date (the next announcement date, per stock)"
    cadence = "every six hours a stock"
    what = ("per stock the alpaca-megacaps and alpaca-options desks trade, the next earnings announcement Nasdaq shows: {date, "
            "estimated (Zacks' estimate from past reporting dates, not the company's own), time (after_close, before_open or "
            "None), eps_forecast, analysts, last_year_eps, announcement}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay; Nasdaq "
                     "publishes no time a date first appeared, so nothing is backfilled and a changed date is a new row")
    every = 6 * 3600.0
    gap = 18 * 3600.0
    max_keys = 32
    timeout = 20.0
    example = "AAPL"
    note = "A date Nasdaq estimates can move; the row that moved it is stamped when the House first saw it."

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        return earnings_tickers(recorder.niches())

    def key_of(self, raw: Any) -> str | None:
        return _ticker_key(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.nasdaq import Nasdaq

        return Nasdaq(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: "FeedRecorder", now: float) -> Mapping[str, Any]:
        from ltcm.data import DataError

        out: dict[str, Any] = {}
        for key in keys:
            try:
                out[key] = fetcher.earnings_date(key)
            except DataError as exc:
                # A page that names no date says the stock has none scheduled there: not a failure.
                out[key] = DataError(f"{NOT_LISTED} {exc}") if "names no date" in str(exc) else exc
            except Exception as exc:  # noqa: BLE001 - a stock whose page fails is a failed poll of that stock
                out[key] = exc
        return out

    def asks(self, words: set[str]) -> bool:
        return _earnings_words(words) and bool(words & _CALENDAR_WORDS)


_TENOR = re.compile(r"^(\d{1,2})\s*-?\s*(M|MO|MON|MONTH|MONTHS|W|WK|WEEK|WEEKS|Y|YR|YRS|YEAR|YEARS)$")


def _tenor_key(raw: Any) -> str | None:
    """A Treasury tenor as the treasury feed names it (`10Y`, `3M`, `6W`) from `10y`, `10-year`, `3 MONTH`."""
    from ltcm.data.rates import TENORS

    found = _TENOR.match(str(raw or "").strip().upper())
    if not found:
        return None
    unit = found.group(2)[0]
    key = f"{int(found.group(1))}{'M' if unit == 'M' else 'W' if unit == 'W' else 'Y'}"
    return key if key in TENORS else None


class ReferenceRates(Source):
    """SOFR and the other reference rates the New York Fed publishes each business day, for Kalshi's
    rates series (KXSOFRD). Its API answers an effective date, never the moment a rate appeared."""

    name = "rates"
    host = "markets.newyorkfed.org"
    source = "nyfed: markets.newyorkfed.org/api/rates/all/latest.json (SOFR, EFFR, OBFR, TGCR, BGCR)"
    cadence = "every 30 minutes (published about 08:00 ET each business day, EFFR about 09:00)"
    what = ("per reference rate (SOFR, EFFR, OBFR, TGCR, BGCR), the newest the New York Fed has published: {type, effective_date, "
            "rate (percent), p1, p25, p75, p99, volume_bn, revised} and EFFR's target_from and target_to")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: the New "
                     "York Fed publishes an effective date, never the moment a rate appeared, so nothing is backfilled")
    batch = True
    every = 1800.0
    gap = 3 * 1800.0
    example = "SOFR"
    note = "effective_date is the business day the rate applies to; it is published the next business day."

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        from ltcm.data.rates import REFERENCE_RATES

        return list(REFERENCE_RATES)

    def key_of(self, raw: Any) -> str | None:
        from ltcm.data.rates import REFERENCE_RATES

        text = str(raw or "").strip().upper()
        return text if text in REFERENCE_RATES else None

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.rates import Rates

        return Rates(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: "FeedRecorder", now: float) -> Mapping[str, Any]:
        from ltcm.data import DataError

        rates = fetcher.reference_rates()
        return {key: rates[key] if key in rates else DataError(f"nyfed rates: no {key} in the answer") for key in keys}

    def asks(self, words: set[str]) -> bool:
        return bool(words & {"sofr", "effr", "obfr", "tgcr", "bgcr"}) or ({"fed", "funds"} <= words and bool(words & {"rate", "rates",
                                                                                                                  "effective"}))


class ParYields(Source):
    """The Treasury's daily par yield curve, for Kalshi's Treasury yield series (KXUST2AD, KXUST10AD).
    Every entry of its feed carries the feed's own `<updated>`, not the moment the day's curve
    appeared (Sept 24, 2026), so a curve is stamped when the House first read it."""

    name = "treasury"
    host = "home.treasury.gov"
    source = "treasury: home.treasury.gov daily_treasury_yield_curve XML (par yields by tenor, the current month's)"
    cadence = "hourly (the day's curve is published after the close)"
    what = ("per tenor (1M, 6W, 2M, 3M, 4M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y), the newest par yield the Treasury has "
            "published: {tenor, date, yield (percent)}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay: the "
                     "Treasury's feed carries no time a curve appeared, so nothing is backfilled")
    batch = True
    every = 3600.0
    gap = 3 * 3600.0
    timeout = 60.0
    example = "10Y"
    note = "date is the business day of the curve."

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        from ltcm.data.rates import TENORS

        return list(TENORS)

    def key_of(self, raw: Any) -> str | None:
        return _tenor_key(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.rates import Rates

        return Rates(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: "FeedRecorder", now: float) -> Mapping[str, Any]:
        from ltcm.data import DataError

        today = datetime.fromtimestamp(now, timezone.utc)
        curves = fetcher.par_yields(today.strftime("%Y%m"))
        if not curves:  # the month's first curve is not out yet: the newest is last month's
            last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y%m")
            curves = fetcher.par_yields(last_month)
        if not curves:
            raise DataError("treasury par yields: no curve published in this month or the last")
        latest = curves[-1]
        return {key: ({"tenor": key, "date": latest["date"], "yield": latest["yields"][key]} if key in latest["yields"]
                      else DataError(f"treasury par yields: no {key} on {latest['date']}")) for key in keys}

    def asks(self, words: set[str]) -> bool:
        return (bool(words & {"treasury", "treasuries", "ust"}) and bool(words & {"yield", "yields", "curve", "par", "rate", "rates"})) \
            or {"par", "yield"} <= words


class SportsOdds(Source):
    """The sportsbook lines and win probabilities of the games on each league's board, from ESPN's
    core API: a second price for every Kalshi game contract. The events are the ones on the House's
    own recorded scoreboard (the `sports` feed), so the two feeds agree on what a game is."""

    name = "odds"
    host = "sports.core.api.espn.com"
    source = ("espn: sports.core.api.espn.com/v2/sports/<sport>/leagues/<league>/events/<id>/competitions/<id>/odds and "
              "/predictor, for the pre-game events of the league's recorded scoreboard")
    cadence = "every 30 minutes a league, for its games starting within 36 hours"
    what = ("per league, each game on its recorded board that has not started and starts within 36 hours: {id, name, start, home, "
            "away, lines: [{provider, details, spread (home-signed), over_under, home_ml, away_ml, implied_home (de-vigged), open: "
            "{spread, home_ml, away_ml}}], win_probability: {home, away, tie, modified} (ESPN's matchup predictor; football and "
            "basketball only, else None)}")
    point_in_time = ("each row is stamped with the House's receive time and shown only from then on, live and in replay; ESPN "
                     "keeps no history of its lines here, so nothing is backfilled")
    every = 1800.0
    gap = 3 * 1800.0
    max_keys = 24
    timeout = 20.0
    example = "nfl"
    note = "A league whose board is not recorded yet has no row; lines is [] for a game no book prices."
    HORIZON = 36 * 3600.0
    MAX_EVENTS = 16
    #: Where ESPN's matchup predictor exists (other sports answer 404).
    PREDICTED = ("football", "basketball")

    def keys(self, recorder: "FeedRecorder") -> list[str]:
        return recorder.keys("sports")

    def key_of(self, raw: Any) -> str | None:
        return _sports_key(raw)

    def fetcher(self, transport: Any, clock: Callable[[], float]) -> Any:
        from ltcm.data.sports import Sports

        return Sports(transport, timeout=self.timeout, clock=clock)

    def poll(self, fetcher: Any, keys: Sequence[str], recorder: "FeedRecorder", now: float) -> Mapping[str, Any]:
        from ltcm.data import DataError

        out: dict[str, Any] = {}
        for league in keys:
            path = SPORTS_LEAGUES.get(league)
            board = ((recorder.latest({"sports": [league]}, now).get("sports") or {}).get(league)) if path else None
            if board is None:
                out[league] = DataError(f"{NOT_LISTED} no {league} scoreboard is recorded yet")
                continue
            games = []
            for event in board.get("events") or []:
                try:
                    start = _epoch(event.get("start"))
                except (TypeError, ValueError):
                    continue
                if event.get("status") == "pre" and now <= start <= now + self.HORIZON:
                    games.append(event)
            rows = []
            try:
                for event in sorted(games, key=lambda e: str(e.get("start")))[:self.MAX_EVENTS]:
                    lines = fetcher.core_odds(path, event["id"])
                    predicted = fetcher.core_predictor(path, event["id"]) if path.split("/")[0] in self.PREDICTED else None
                    rows.append({"id": event["id"], "name": event.get("name"), "start": event.get("start"),
                                 "home": (event.get("home") or {}).get("team"), "away": (event.get("away") or {}).get("team"),
                                 "lines": lines, "win_probability": predicted})
            except Exception as exc:  # noqa: BLE001 - one game's lines that fail fail the league's poll: never a partial board
                out[league] = exc
                continue
            out[league] = {"league": league, "events": rows}
        return out

    def asks(self, words: set[str]) -> bool:
        if words & {"outcome", "outcomes", "resolved", "settlement", "settled", "kalshi", "consensus"}:
            return False
        sporting = bool(words & _SPORTS_CONTEXT) or bool(words & {"nfl", "ncaaf", "mlb", "nba", "nhl", "wnba", "epl", "mls"})
        priced = bool(words & {"odds", "moneyline", "moneylines", "sportsbook", "sportsbooks", "betting", "vegas", "bookmaker",
                               "bookmakers"}) or ("win" in words and bool(words & {"probability", "probabilities", "prob"}))
        return sporting and priced


def _register(*sources: Source) -> dict[str, Source]:
    return {source.name: source for source in sources}


#: The recorders of Sept 24, 2026, in the brief's order of priority (weather first: it is the input
#: of the one proven family). What a strategy may declare in `NEEDS["feeds"]` beside the first four.
RECORDERS: dict[str, Source] = _register(WeatherEnsemble(), NwsForecast(), ForecastHistory(), EarningsHistory(), EarningsDate(),
                                         ReferenceRates(), ParYields(), SportsOdds())
FEEDS = FEEDS + tuple(RECORDERS)
HISTORY_FEEDS = HISTORY_FEEDS + tuple(name for name, source in RECORDERS.items() if source.history)
for _feed_name, _recorder in RECORDERS.items():
    SOURCES[_feed_name] = _recorder.source
    CADENCE[_feed_name] = _recorder.cadence
    WHAT[_feed_name] = _recorder.what
    POINT_IN_TIME[_feed_name] = _recorder.point_in_time
    GAP_SECONDS[_feed_name] = _recorder.gap
    LOOKBACK_DAYS[_feed_name] = _recorder.lookback_days
del _feed_name, _recorder


def _empty_stats() -> dict[str, Any]:
    return {"first_ok": None, "last_ok": None, "last_good": None, "last_poll": None, "last_error": None, "polls": 0, "ok": 0,
            "snapshots": 0}
