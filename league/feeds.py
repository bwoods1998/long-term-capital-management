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
from datetime import datetime, timezone
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
    `perps`, `vol`, `funding`), at most `MAX_KEYS` keys each in the order declared, league names in
    lower case (`nfl`, or a Kalshi series such as `KXNFLGAME`, or an ESPN path) and coins in upper
    case (`BTC`, `BTC/USD`, `XBT`). A league no Kalshi series maps, a coin no crypto desk trades and
    a DVOL other than BTC's and ETH's are dropped, never guessed. Anything else yields {}."""
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
    interest is not a perp's), Deribit's DVOL or a crypto implied volatility (`vol`), or the
    history of perpetual funding (`funding`: the only history, with DVOL's, the House holds)."""
    words = set(re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_").split("_")) - {""}
    if not words or words & (_NOT_FEEDS - _HISTORY):
        return None
    if "dvol" in words or ("implied" in words and words & _VOL_WORDS and words & _VOL_COINS):
        return "vol"
    if "funding" in words and words & _PERPS_CONTEXT:
        return "funding" if words & (_HISTORY | _SETTLED) else "perps"
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
    between history pages (tests give one that does not), and `backfill_pages` caps a backfill pass."""

    def __init__(self, house: Any = None, path: str | Path | None = None, transports: Any = None, *,
                 clock: Callable[[], float] | None = None, ledger: Any = None, alert: Callable[[str, str], None] | None = None,
                 niches: Mapping[str, Any] | None = None, keys: Mapping[str, Sequence[str]] | None = None,
                 sleep: Callable[[float], None] | None = None, backfill_pages: int = BACKFILL_PAGES):
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
        """What this House polls for `feed` now (the survey moves the universes, so it is asked each time)."""
        if self._keys is not None:
            return list(self._keys.get(feed) or [])
        if feed == "sports":
            return sports_plan(self.niches())[0]
        if feed in ("perps", "funding"):
            return perp_coins(self.niches())
        if feed == "vol":
            return list(VOL_KEYS)
        return []

    def unmapped(self) -> list[str]:
        return sports_plan(self.niches())[1]

    def _plan(self) -> list[tuple[str, str]]:
        plan = [("sports", league) for league in self.keys("sports")]
        for feed in ("perps", *HISTORY_FEEDS):
            if self.keys(feed):
                plan.append((feed, "*"))
        if self._backfill_pending():
            plan.append(("backfill", "*"))  # last: every live poll due goes first
        return plan

    def _fetcher(self, feed: str) -> Any:
        fetcher = self._fetchers.get(feed)
        if fetcher is None:
            transport = self._transports.get(feed) if isinstance(self._transports, Mapping) else self._transports
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
                else:
                    self._poll_history(feed, out)
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
        """One pass of `vol` or `funding`: for each key, every completed candle or settled rate newer
        than the newest row held (`_fetch_head`), stamped when it became final. Scheduled 90 seconds
        past the next hour (vol) or half hour (funding), or sooner when a key failed."""
        every = VOL_SECONDS if feed == "vol" else FUNDING_SECONDS
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
                failed = failed or UNLISTED not in error
        out["polled"].append(feed)
        finished = self.clock()
        nxt = _aligned(finished, every)
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
        return now - (self.backfill_days() + LOOKBACK_DAYS[feed]) * 86400.0

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
        """Did OKX answer, less than `UNLISTED_SECONDS` ago, that it lists no such instrument?"""
        with self._lock:
            row = self._history_state().get((feed, key))
        return bool(row) and UNLISTED in str(row.get("error") or "") and now - float(row.get("updated") or 0.0) < UNLISTED_SECONDS

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
            (feed, key, first - LOOKBACK_DAYS[feed] * 86400.0, end))]
        if not rows:
            return []
        with self._lock:
            since = (self._load_stats().get((feed, key)) or {}).get("first_ok")
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
        out["request"] = ("NEEDS['feeds'] = {'sports': ['nfl', 'mlb'], 'perps': ['BTC', 'ETH'], 'vol': ['BTC'], 'funding': ['BTC', 'SOL']} "
                          "(known names only, at most six each; a Kalshi series such as KXNFLGAME names its league) adds "
                          "ctx['feeds'][feed][key]: the latest row stamped at or before now -- sports and perps with when the House "
                          "received them, vol and funding with when they became final (a candle's close, a rate's settlement). A key "
                          "that is absent is unavailable; a strategy must also work when ctx['feeds'] is absent.")
        out["replay"] = (f"Rows are replayed point in time by t. sports and perps are recorded live and nothing before recording "
                         f"began exists: a strategy that declares them is replayed only once every declared key has {need} blocks of "
                         f"its horizon recorded ({need} hours for an hour strategy, {need} days for a day strategy), and until then its "
                         "replay is refused as unsupported input, which is not a trial. vol and funding are point-in-time history, "
                         "backfilled from the venues' own history over the replay window and stamped when each value became final, "
                         "so a strategy that declares them is replayed at once (see replayable_now). Live wakes are handed every "
                         "feed at once.")
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


def _empty_stats() -> dict[str, Any]:
    return {"first_ok": None, "last_ok": None, "last_good": None, "last_poll": None, "last_error": None, "polls": 0, "ok": 0,
            "snapshots": 0}
