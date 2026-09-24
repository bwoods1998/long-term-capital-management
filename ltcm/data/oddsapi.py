"""The Odds API: moneylines across US sportsbooks, for a consensus win probability (kalshi-sports).

A PAID key the OWNER places (`ODDS_API_KEY` in the House box's `.env`, never in the repository);
until then the House's `consensus` recorder waits and polls nothing (league/feeds.py). Each call
costs the owner credits (one per region per market), so the recorder asks once every few hours per
league. The key rides in the query string, so the recorder redacts it from every error.

    GET https://api.the-odds-api.com/v4/sports/<sport key>/odds?apiKey=<key>&regions=us&markets=h2h
        &oddsFormat=american
      [ {id, sport_key, commence_time, home_team, away_team,
         bookmakers: [{key, title, last_update, markets: [{key: "h2h", last_update,
                       outcomes: [{name, price}]}]}]} ]
      (https://the-odds-api.com/liveapi/guides/v4/; UNVERIFIED on a probe: no key on Sept 24, 2026)

`consensus` is the mean, across the books that price a game, of each book's implied probabilities
once its margin is taken out (each outcome's implied probability over the book's sum).
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Any, Mapping

from . import CONTACT_USER_AGENT, DataError, HttpTransport, read_json, require

HOST = "https://api.the-odds-api.com"
#: The House's league keys (league/feeds.py SPORTS_LEAGUES) -> The Odds API's sport keys.
SPORTS = {
    "nfl": "americanfootball_nfl", "ncaaf": "americanfootball_ncaaf", "mlb": "baseball_mlb", "nba": "basketball_nba",
    "wnba": "basketball_wnba", "nhl": "icehockey_nhl", "epl": "soccer_epl", "mls": "soccer_usa_mls",
    "laliga": "soccer_spain_la_liga", "seriea": "soccer_italy_serie_a", "bundesliga": "soccer_germany_bundesliga",
    "ligue1": "soccer_france_ligue_one", "championship": "soccer_efl_champ", "ligamx": "soccer_mexico_ligamx",
    "eredivisie": "soccer_netherlands_eredivisie", "ligaportugal": "soccer_portugal_primeira_liga", "scottishprem": "soccer_spl",
}
MIN_INTERVAL = 1.0


def _implied(price: Any) -> float | None:
    try:
        value = float(price)
    except (TypeError, ValueError):
        return None
    if value >= 100:
        return 100.0 / (value + 100.0)
    if value <= -100:
        return -value / (-value + 100.0)
    return None


def parse_odds(payload: Any) -> list[dict[str, Any]]:
    """The Odds API's h2h answer as one row per game: `{id, commence_time, home, away, books,
    consensus: {home, away, draw?}, last_update}` -- `books` the number that priced it, `consensus`
    their mean de-vigged probabilities (None when no book priced it)."""
    require(isinstance(payload, list), "the odds api: not a list of games" + (f" ({payload.get('message')})"
                                                                               if isinstance(payload, Mapping) else ""))
    out = []
    for game in payload:
        if not isinstance(game, Mapping) or not game.get("id"):
            continue
        home, away = str(game.get("home_team") or ""), str(game.get("away_team") or "")
        sums: dict[str, float] = {}
        books, updates = 0, []
        for book in game.get("bookmakers") if isinstance(game.get("bookmakers"), list) else []:
            market = next((m for m in book.get("markets") or [] if isinstance(m, Mapping) and m.get("key") == "h2h"), None) \
                if isinstance(book, Mapping) else None
            if market is None:
                continue
            raw = {str(o.get("name")): _implied(o.get("price")) for o in market.get("outcomes") or [] if isinstance(o, Mapping)}
            if not raw or any(p is None for p in raw.values()) or home not in raw or away not in raw:
                continue
            total = sum(raw.values())
            for name, p in raw.items():
                side = "home" if name == home else "away" if name == away else "draw"
                sums[side] = sums.get(side, 0.0) + p / total
            books += 1
            updates.append(str(market.get("last_update") or book.get("last_update") or ""))
        out.append({"id": str(game["id"]), "commence_time": game.get("commence_time"), "home": home, "away": away, "books": books,
                    "consensus": {side: round(value / books, 4) for side, value in sums.items()} if books else None,
                    "last_update": max(updates) if updates else None})
    return out


class OddsApi:
    """Moneylines across US books, read with the owner's paid key."""

    def __init__(self, api_key: str, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        if not api_key:
            raise DataError("the odds api: no key (ODDS_API_KEY is the owner's to place)")
        self.api_key = str(api_key)
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def odds(self, league: str) -> list[dict[str, Any]]:
        sport = SPORTS.get(str(league or "").lower())
        if sport is None:
            raise DataError(f"the odds api: no sport for {league!r}")
        params = {"apiKey": self.api_key, "regions": "us", "markets": "h2h", "oddsFormat": "american"}
        url = f"{HOST}/v4/sports/{sport}/odds?" + urllib.parse.urlencode(params)
        return parse_odds(read_json(self.transport, url, headers={"Accept": "application/json"}, timeout=self.timeout,
                                    what=f"the odds api {league}"))


__all__ = ["HOST", "OddsApi", "SPORTS", "parse_odds"]
