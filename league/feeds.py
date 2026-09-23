"""Live feeds the House records for its strategies: ESPN scoreboards, and perpetual funding and
open interest.

Measured on the production ledger, Sept 22, 2026: 43 agents had asked for live sports scores or
game state and 32 for crypto perpetual funding rates or open interest -- in tool requests, in
research summaries ("the perpetual funding/OI feed remains not_supplied") and in paid consults.
The fetchers had existed since the arena of Sept 18 (`ltcm/data/sports.py`, `ltcm/data/derivs.py`)
and the House box could reach their hosts, but nothing in `league/` called them: no strategy could
read either, live or in replay.

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

THREE RULES KEEP IT HONEST (as in `league/options_history.py`).

1. **Point in time.** A row is stamped `t` with when the House RECEIVED it (its clock once the
   fetch returned, rounded up to the millisecond), and it is visible at a moment only if it was
   received at or before it -- live (`latest`) and in replay (`series`, `league/replay.py`) alike.
   Nothing is backfilled, so a replay can use these feeds only over the time they have been
   recorded: the House replays a strategy that declares them only once they span the replay
   gate's `min_blocks` blocks of its horizon, and refuses it as unsupported input (not a trial)
   until then.
2. **Nothing is fabricated.** A source that fails is a `polls` row with ok=0 and its error, and
   nothing is stored for it. A key the House does not record is absent from `ctx["feeds"]`: it is
   unavailable, never an empty or zero row.
3. **Unchanged content is stored once.** A poll whose content has the digest of the key's last
   snapshot adds a `polls` row and no snapshot: a quiet scoreboard costs almost nothing, and a
   row's `t` is when that content was FIRST received.

Standard library only (and `ltcm.data` for the fetchers). One sqlite connection per thread: the
store is written by the House's feeds lane and read by wake threads, the replay lane and research.
"""

from __future__ import annotations

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
FEEDS = ("sports", "perps")
#: What one strategy may ask for, per feed (as `NEEDS["observe"]` allows six of each).
MAX_KEYS = 6
SPORTS_LIVE_SECONDS = 60
SPORTS_QUIET_SECONDS = 900
#: A board with a game starting this soon is polled as if the game were on.
SPORTS_SOON_SECONDS = 90 * 60
PERPS_SECONDS = 300
#: A source that failed is asked again this soon (a live board keeps its minute).
RETRY_SECONDS = 300
#: One warning per feed per hour at most, and never an error: an error alert inside a release's
#: watch rolls the release back, and a scoreboard that is down says nothing about the release.
ALERT_SECONDS = 3600
COVERAGE_SECONDS = 3600
#: How long one successful poll counts as coverage when the next is late (twice the quiet
#: cadence for a scoreboard, three polls for perps): a House that was down covers nothing.
GAP_SECONDS = {"sports": 2 * SPORTS_QUIET_SECONDS, "perps": 3 * PERPS_SECONDS}
#: The feed rows one replay tape may carry, as JSON. A tape is handed whole to a sealed box, and
#: seven-week sports tapes were killed for memory (exit 137) on Sept 19, 2026: a key over its share
#: is sampled at a coarser step instead.
TAPE_BYTES = 8 * 1024 * 1024
TIMEOUT = 10.0
#: The replay refusal that means "recorded, not yet long enough" (`House._replay_own` treats it as a
#: wait, not as a replay that could not run).
WAITING = "unsupported input: feeds recorded live since"

SOURCES = {
    "sports": "espn: site.api.espn.com/apis/site/v2/sports/<league>/scoreboard (today's board only)",
    "perps": "okx, hyperliquid, kraken futures, deribit (ltcm/data/derivs.py Derivatives.snapshot)",
}
CADENCE = {
    "sports": "every 60 s while a game of the league is live or starts within 90 minutes, else every 15 minutes",
    "perps": "every 5 minutes",
}
WHAT = {
    "sports": "ESPN scoreboards: every game on the league's current board with status (pre/in/post), score, period, "
              "clock, start time, records and the sportsbook line (spread, total, moneylines)",
    "perps": "per coin: OKX (8-hour funding rate, next rate, premium, open interest in USD, last price), Hyperliquid and "
             "Kraken (1-hour funding rate, open interest, mark), Deribit DVOL (BTC and ETH only) and the OKX funding z-score",
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
    """Every coin a strategy may ask the perps feed for: those of the desks listed in niches.json."""
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


def _perps_key(raw: Any) -> str | None:
    text = str(raw or "").strip().upper()
    if not text or len(text) > 32:
        return None
    coin = re.split(r"[/\-_: ]", text, maxsplit=1)[0]
    coin = PERP_ALIASES.get(coin, coin)
    known = known_perps()
    if coin in known:
        return coin
    for suffix in ("USDT", "USDC", "USD", "PERP"):  # BTCUSD, BTCPERP
        if coin.endswith(suffix) and PERP_ALIASES.get(coin[: -len(suffix)], coin[: -len(suffix)]) in known:
            return PERP_ALIASES.get(coin[: -len(suffix)], coin[: -len(suffix)])
    return None


def requested(value: Any) -> dict[str, list[str]]:
    """`NEEDS["feeds"]` held to what the House can record: known feed names only (`sports`,
    `perps`), at most `MAX_KEYS` keys each in the order declared, league names in lower case
    (`nfl`, or a Kalshi series such as `KXNFLGAME`, or an ESPN path) and coins in upper case (`BTC`,
    `BTC/USD`, `XBT`). A league no Kalshi series maps and a coin no crypto desk trades are dropped,
    never guessed. Anything else yields {}."""
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
            key = _sports_key(raw) if name == "sports" else _perps_key(raw)
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
#: Words that make a request about something the House does not record: line-ups, injuries,
#: player props, history before recording began, or a sport no scoreboard here covers.
_NOT_FEEDS = frozenset(("lineup", "lineups", "injury", "injuries", "inactive", "inactives", "prop", "props", "player",
                        "players", "history", "historical", "backfill", "archive", "archived", "tennis", "atp", "wta",
                        "cricket", "esports", "lol", "cs2", "dota", "dota2", "valorant", "ufc", "mma", "golf", "f1",
                        "nascar", "boxing", "ncaab"))


def request_feed(name: Any) -> str | None:
    """The feed a `tool.request` name plainly asks for, or None. Conservative on purpose: the
    name (as `Commons.request_tool` stores it) must name live scores or a scoreboard with a sports
    word, or perpetual funding or open interest with a derivatives word (a Kalshi market's open
    interest is not a perp's)."""
    words = set(re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_").split("_")) - {""}
    if not words or words & _NOT_FEEDS:
        return None
    if "funding" in words and words & _PERPS_CONTEXT:
        return "perps"
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


# ------------------------------------------------------------------------------ the recorder
class FeedRecorder:
    """Records the live feeds and answers for them.

    `house` supplies the clock, the ledger, the alert line and the desks' universes (`house.niches`,
    live series included); without one, give `clock` and `ledger` (and `niches`, or niches.json is
    read). `transports` is the HTTP transport of each feed's fetcher ({"sports": ..., "perps": ...},
    or one object for both; tests give `ltcm.tests.fakes.FakeTransport`); None leaves each fetcher
    its own `HttpTransport`. `keys` overrides what is polled ({"sports": [...], "perps": [...]})."""

    def __init__(self, house: Any = None, path: str | Path | None = None, transports: Any = None, *,
                 clock: Callable[[], float] | None = None, ledger: Any = None, alert: Callable[[str, str], None] | None = None,
                 niches: Mapping[str, Any] | None = None, keys: Mapping[str, Sequence[str]] | None = None):
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
        self._fetchers: dict[str, Any] = {}
        self._lock = threading.RLock()  # one writer at a time in this process, and the counters below
        self._local = threading.local()
        self._connections: list[tuple[threading.Thread, Any]] = []
        self._next: dict[tuple[str, str], float] = {}  # (feed, key) -> when it is due; perps poll as one ("perps", "*")
        self._hot: dict[str, bool] = {}  # league -> was a game live or near at its last good poll
        self._warned: dict[str, float] = {}
        self._covered: dict[str, int] = {}  # feed -> the hour whose coverage row is on the ledger
        self._stats: dict[tuple[str, str], dict[str, Any]] | None = None
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
        if feed == "perps":
            return perp_coins(self.niches())
        return []

    def unmapped(self) -> list[str]:
        return sports_plan(self.niches())[1]

    def _plan(self) -> list[tuple[str, str]]:
        plan = [("sports", league) for league in self.keys("sports")]
        if self.keys("perps"):
            plan.append(("perps", "*"))
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
        """Is a league or the perps pass due now? Cheap, and never raises: the tick asks every minute."""
        if self._closed:
            return False
        try:
            now = self.clock()
            with self._lock:
                return any(self._next.get(item, 0.0) <= now for item in self._plan())
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
        """Poll whatever is due and record it. The House calls this on its feeds lane; it never
        raises: a source that fails is a failed poll, and a warning at most hourly."""
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
                else:
                    self._poll_perps(out)
            self._after_pass(out)
        except Exception as exc:  # noqa: BLE001 - the recorder must never take its lane or the tick down
            out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            self._warn("recorder", f"the feed recorder failed a pass ({out['error']})")
        return out

    def _schedule(self, feed: str, key: str, at: float) -> None:
        with self._lock:
            self._next[(feed, key)] = at

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

    # -- the store -------------------------------------------------------------------------------
    def record(self, feed: str, key: str, *, started: float, finished: float, payload: Any = None, error: str | None = None) -> bool:
        """Keep one poll: always its `polls` row; its content only when it differs from the key's
        last snapshot. `finished` -- the House's clock once the fetch returned, rounded up to the
        millisecond -- is the content's availability stamp. Returns whether a snapshot was stored."""
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
                row["last_ok"] = received
                row["last_error"] = None
            else:
                row["last_error"] = failure
            row["snapshots"] += int(changed)
        return changed

    def _load_stats(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Per (feed, key) counters, read from the store once and kept current by `record` (health
        is written every tick, and a GROUP BY over every poll ever is not a tick's work)."""
        with self._lock:
            if self._stats is None:
                stats: dict[tuple[str, str], dict[str, Any]] = {}
                for feed, key, first_ok, last_ok, last_poll, polls, oks in self.db.execute(
                        "SELECT feed, key, MIN(CASE WHEN ok = 1 THEN finished END), MAX(CASE WHEN ok = 1 THEN finished END), "
                        "MAX(finished), COUNT(*), SUM(ok) FROM polls GROUP BY feed, key"):
                    stats[(feed, key)] = {**_empty_stats(), "first_ok": first_ok, "last_ok": last_ok, "last_poll": last_poll,
                                          "polls": int(polls or 0), "ok": int(oks or 0)}
                for feed, key, count in self.db.execute("SELECT feed, key, COUNT(*) FROM snapshots GROUP BY feed, key"):
                    stats.setdefault((feed, key), _empty_stats())["snapshots"] = int(count)
                for (feed, key), row in stats.items():
                    if row["last_poll"] is not None and row["last_poll"] != row["last_ok"]:
                        found = self.db.execute("SELECT error FROM polls WHERE feed = ? AND key = ? ORDER BY finished DESC LIMIT 1",
                                                (feed, key)).fetchone()
                        row["last_error"] = found[0] if found else None
                self._stats = stats
            return self._stats

    @staticmethod
    def _row(received: float, blob: bytes) -> dict[str, Any]:
        return {**json.loads(gzip.decompress(blob).decode("utf-8")), "t": stamp(received)}

    # -- reads -----------------------------------------------------------------------------------
    def latest(self, wanted: Any, now: Any) -> dict[str, dict[str, dict[str, Any]]]:
        """What a live wake is handed: for each declared key the last row received at or before
        `now`, stamped `t` with when it was received. A key with nothing received is absent."""
        now_ts = _epoch(now)
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for feed, keys in requested(wanted).items():
            for key in keys:
                row = self.db.execute("SELECT received, payload FROM snapshots WHERE feed = ? AND key = ? AND received <= ? "
                                      "ORDER BY received DESC LIMIT 1", (feed, key, now_ts)).fetchone()
                if row is not None:
                    out.setdefault(feed, {})[key] = self._row(row[0], row[1])
        return out

    def series(self, wanted: Any, start: Any, end: Any, step_seconds: float, *,
               max_bytes: int = TAPE_BYTES) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """The rows a replay tape carries over [start, end], by feed and key, oldest first, each
        stamped `t` with when it was received. Only rows received at or before `end`; the row
        received last at or before `start` opens each series, so the first step sees what a wake
        would have. At most one row a step (`_thin`), and a key whose rows would take more than its
        share of `max_bytes` is sampled at twice the step until it fits: a coarser view of the
        past, never a look at the future. The replay shows a row only from its `t` on."""
        plan = requested(wanted)
        start_ts, end_ts = _epoch(start), _epoch(end)
        step = max(1.0, float(step_seconds or 300))
        keys = [(feed, key) for feed, rows in plan.items() for key in rows]
        share = max(1.0, float(max_bytes)) / max(1, len(keys))
        out: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for feed, key in keys:
            opening = self.db.execute("SELECT received, payload FROM snapshots WHERE feed = ? AND key = ? AND received <= ? "
                                      "ORDER BY received DESC LIMIT 1", (feed, key, start_ts)).fetchall()
            rows = opening + self.db.execute("SELECT received, payload FROM snapshots WHERE feed = ? AND key = ? AND received > ? "
                                             "AND received <= ? ORDER BY received", (feed, key, start_ts, end_ts)).fetchall()
            if not rows:
                continue
            texts: dict[int, str] = {}

            def text(index: int) -> str:
                if index not in texts:
                    texts[index] = gzip.decompress(rows[index][1]).decode("utf-8")
                return texts[index]

            width = step
            while True:
                picked = _thin([row[0] for row in rows], width, keep_first=bool(opening))
                if len(picked) <= 1 or sum(len(text(i)) + 40 for i in picked) <= share:
                    break
                width *= 2
            out.setdefault(feed, {})[key] = [{**json.loads(text(i)), "t": stamp(rows[i][0])} for i in picked]
        return out

    def coverage(self, wanted: Any = None, start: Any = None, end: Any = None) -> dict[str, dict[str, dict[str, Any]]]:
        """Per feed and key: whether the House polls it, when recording began (its first successful
        poll) and its last, the counts, and -- over [start, end] when both are given -- the seconds
        covered: each successful poll covers until the next, for at most the feed's `GAP_SECONDS`."""
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
                if window is not None:
                    entry["window"] = [stamp(window[0]), stamp(window[1])]
                    entry["covered_seconds"] = round(self._covered_seconds(feed, key, *window), 3) if row["first_ok"] is not None else 0.0
                out.setdefault(feed, {})[key] = entry
        return out

    def _covered_seconds(self, feed: str, key: str, start: float, end: float) -> float:
        gap = float(GAP_SECONDS.get(feed, SPORTS_QUIET_SECONDS))
        times = [t for (t,) in self.db.execute("SELECT finished FROM polls WHERE feed = ? AND key = ? AND ok = 1 AND finished > ? "
                                               "AND finished <= ? ORDER BY finished", (feed, key, start - gap, end))]
        covered = 0.0
        for index, at in enumerate(times):
            upto = min(times[index + 1] if index + 1 < len(times) else end, at + gap, end)
            since = max(at, start)
            if upto > since:
                covered += upto - since
        return covered

    # -- what the House says about it ------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        """What `House.research_capabilities` announces: what is recorded, since when, how often, and
        what a replay of a strategy that reads it needs."""
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
        out["sports"]["unmapped_series"] = self.unmapped()[:40]
        out["request"] = ("NEEDS['feeds'] = {'sports': ['nfl', 'mlb'], 'perps': ['BTC', 'ETH']} (known names only, at most six "
                          "each; a Kalshi series such as KXNFLGAME names its league) adds ctx['feeds'][feed][key]: the latest row "
                          "received at or before now, stamped t with when the House received it. A key that is absent is "
                          "unavailable; a strategy must also work when ctx['feeds'] is absent.")
        out["replay"] = (f"Rows are replayed point in time by their receive time t, and nothing before recording began exists. A "
                         f"strategy that declares feeds is replayed only once every declared key has {need} blocks of its horizon "
                         f"recorded ({need} hours for an hour strategy, {need} days for a day strategy); until then its replay is "
                         "refused as unsupported input, which is not a trial. Live wakes are handed the feeds at once.")
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
            out["sports"]["live_boards"] = sorted(league for league, live in hot.items() if live)
            out["sports"]["unmapped_series"] = len(self.unmapped())
            out["perps"]["venues_answering"] = venues
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
            sample = "; ".join(f"{key}: {error[:120]}" for key, error in rows[:3])
            self._warn(feed, f"feeds: {len(rows)} of {polled} {feed} polls failed ({sample})")
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
            payload: dict[str, Any] = {
                "asset": "feed", "feed": feed, "source": SOURCES[feed], "cadence": CADENCE[feed],
                "status": "unavailable" if not firsts else "partial" if failing else "current",
                "start": stamp(min(firsts)) if firsts else None, "end": stamp(max(lasts)) if lasts else None,
                "keys": {key: {"first": stamp(row["first_ok"]) if row["first_ok"] is not None else None,
                               "last": stamp(row["last_ok"]) if row["last_ok"] is not None else None,
                               "polls": row["polls"], "ok": row["ok"], "snapshots": row["snapshots"],
                               **({"error": str(row["last_error"])[:160]} if row["last_error"] else {})}
                         for key, row in rows.items()},
                "point_in_time": "each row is stamped with the House's receive time and shown only from then on, live and in "
                                 "replay; nothing is backfilled, and ESPN is never asked for a past date",
                "recorded_at": stamp(now),
            }
            if feed == "sports":
                payload["unmapped_series"] = self.unmapped()[:60]
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
        gate counts a `tool.fulfilled` for its line). A feed with no successful poll has not shipped.
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
        else:
            head = (f"Shipped (league/feeds.py): the House records perpetual funding and open interest (OKX, Hyperliquid, Kraken), "
                    f"Deribit DVOL (BTC, ETH) and the OKX funding z-score for {keys}, {CADENCE['perps']}, since {since}. Declare "
                    "NEEDS['feeds'] = {'perps': ['BTC', ...]} (at most six) and read ctx['feeds']['perps'][coin].")
        return (head + " Each row carries t, when the House received it; an absent key is unavailable. A replay shows the rows "
                f"point in time and accepts a strategy that declares them once {need} blocks of its horizon are recorded.")


def _empty_stats() -> dict[str, Any]:
    return {"first_ok": None, "last_ok": None, "last_poll": None, "last_error": None, "polls": 0, "ok": 0, "snapshots": 0}
