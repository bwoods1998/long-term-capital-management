"""ESPN scoreboards and game summaries for Kalshi's sports markets.

Kalshi lists a market on most major-league games ("Will the Chiefs beat the Ravens?"). ESPN's
site API publishes the same games with their status, score, clock, the sportsbook line and,
during a game, a win probability. A desk that reads the line before kickoff and the win
probability during the game has a second price for every Kalshi contract on the board.

One host, keyless (https://site.api.espn.com; undocumented but stable for years). ESPN's edge
answers some default Python User-Agents with 403, so every request identifies as `curl/8.0`.
Endpoints and the fields relied on (probed live Sept 18, 2026):

    GET /apis/site/v2/sports/{sport}/{league}/scoreboard
        events[]: id, name, shortName, date (ISO Z), competitions[0]:
            status.type.state (pre|in|post), status.period, status.displayClock
            competitors[]: homeAway, score (string), winner, records[0].summary,
                           team.displayName, team.abbreviation, team.location, team.name
            odds[0]: details ("CAR -2.5"), overUnder, spread (favorite's margin, positive),
                     homeTeamOdds.favorite, awayTeamOdds.favorite,
                     moneyline.home.close.odds ("+130"), moneyline.away.close.odds,
                     provider.name
                     (soccer rows carry details and overUnder only)
    GET /apis/site/v2/sports/{sport}/{league}/summary?event={id}
        header.competitions[0]: the same competitor and status shape (records under `record`)
        winprobability[]: homeWinPercentage, tiePercentage (last element is current)
        pickcenter[0]: spread, overUnder, homeTeamOdds.moneyLine, awayTeamOdds.moneyLine
        predictor.homeTeam.gameProjection / predictor.awayTeam.gameProjection (percent strings)
        drives.current.plays[] / drives.previous[].plays[] (football) or plays[] (other sports):
            text, period.number, clock.displayValue

Every value in a result is a str, float, int, bool or None so a row ships as JSON. Odds are
American moneylines as signed ints and the spread is signed from the home side (negative when
the home team is favored).

Sept 24, 2026 (the House's `odds` recorder, league/feeds.py): ESPN's core API carries what the
scoreboard does not -- every provider's line with its opening and current prices, and the
matchup predictor's win probability. Probed that day:

    GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/odds
        items[]: provider {id, name, priority}, details ("GB -5.5"), spread (home-signed), overUnder,
                 homeTeamOdds / awayTeamOdds: favorite, moneyLine (current), open {pointSpread.american,
                 moneyLine.american}, current {...}
    GET .../events/{id}/competitions/{id}/predictor
        lastModified, homeTeam / awayTeam .statistics[]: gameProjection (win %), teamChanceTie (%)
        (football and basketball; other sports answer 404)

Sept 25, 2026 (the Kalshi-scale run, K1), probed live that morning:

- The college-football scoreboard with no query is ESPN's FEATURED board: 18 games of week 4, while
  Kalshi listed 113 KXNCAAFSPREAD events (FBS and FCS). `?groups=80` is the whole FBS week (71
  games) and `?groups=81` the whole FCS week (65; 13 games are on both), and `limit=300` changes
  nothing today but keeps a big week whole. The union matched all 346 NCAAF events Kalshi listed for
  Sept 25-28.
- A daily league's board (baseball, soccer, hockey, basketball) with no query is ONE day, and not
  always today: at 06:18Z Sept 25 MLB's was still Sept 24 (every game final), and the Premier
  League's was its last matchday, Sept 20, during an international break (which is why the `sports`
  store held one EPL snapshot from Sept 23 on: the board never changed). `?dates=YYYYMMDD` (one New
  York date; a range answers no events) gives that day's games: MLB listed 17 for Sept 25 and 14 for
  Sept 26. `Sports.board` reads either and says which day a daily board is (`day`).
- The core API's odds carry more than `parse_core_odds` kept: `overOdds` / `underOdds` (the total's
  prices), each side's `spreadOdds` (or, for baseball's run line, `current.spread.american`), and on
  soccer `drawOdds.moneyLine`, the draw's price: the two sides' moneylines are then three-way prices.
  ONE provider (DraftKings) answered for every NFL, NCAAF, MLB and MLS game probed.

Sept 25, 2026, later (the Kalshi-scale run, K1c: which individual sports ESPN can PRICE), probed live:

- MMA (`mma/ufc`): the board is the next CARD, one event with a competition a bout (12 on the Sept 26
  Fight Night), each with its own start (prelims 21:00Z, main card 00:00Z) and two `athlete`
  competitors with `order` 1 and 2 and no `homeAway`; `dates=YYYYMMDD` gives a day's card (none on a
  day without one). The core API prices each bout at `.../events/{card}/competitions/{bout}/odds`
  (the bout's id alone answers 404): DraftKings' moneylines on 10 of the 12, under
  `homeAthleteOdds` / `awayAthleteOdds` with each athlete's `$ref`; the home athlete was order 1 on
  all ten. `event_rows` makes a card a row a bout, and `parse_core_odds` reads athlete prices.
- Tennis (`tennis/atp`, `tennis/wta`): the board lists tournaments with `groupings` of matches, but
  the core API's odds were EMPTY for every match probed (ATP Chengdu and Hangzhou, WTA Seoul and
  Singapore, Medvedev's and Andreeva's included); ITF is not on ESPN. Golf (`golf/pga`, `golf/eur`,
  `golf/lpga`) and F1 (`racing/f1`): no odds on the tournament or the race, and no futures. Cricket:
  scoreboards by numeric league id with `odds` [], and the core API refuses cricket leagues. None of
  those is read here: a board without a line prices nothing.
"""

from __future__ import annotations

import re
import time
from typing import Any, Mapping

from . import DataError, HttpTransport, iso, read_json, require

HOST = "https://site.api.espn.com"
CORE_HOST = "https://sports.core.api.espn.com"
#: ESPN's edge refuses some Python User-Agents; a curl one is answered.
USER_AGENT = "curl/8.0"
SOURCE = "espn"
#: ESPN publishes no limit for this host; two a second is polite.
MIN_INTERVAL = 0.5

LEAGUES: dict[str, str] = {
    "nfl": "football/nfl",
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "ncaaf": "football/college-football",
    "ncaab": "basketball/mens-college-basketball",
    "mls": "soccer/usa.1",
    "epl": "soccer/eng.1",
}

_TOKEN = re.compile(r"[a-z0-9]+")


def _text(value: Any) -> "str | None":
    return str(value) if isinstance(value, str) and value else None


def _float(value: Any) -> "float | None":
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _int(value: Any) -> "int | None":
    number = _float(value)
    return int(number) if number is not None else None


def _moneyline(value: Any) -> "int | None":
    """`"+130"` / `"-155"` / `130` -> a signed int; `"EVEN"` -> 100."""
    if isinstance(value, str) and value.strip().upper() == "EVEN":
        return 100
    return _int(str(value).replace("+", "")) if value not in (None, "") else None


def league_path(league: str) -> str:
    key = str(league or "").strip().lower()
    path = LEAGUES.get(key)
    if path is None and "/" in key:
        path = key
    require(path is not None, f"sports: unknown league {league!r}; known: {', '.join(LEAGUES)}")
    return path


def _competitor(row: Any) -> "dict[str, Any] | None":
    if not isinstance(row, Mapping):
        return None
    team = row.get("team") if isinstance(row.get("team"), Mapping) else {}
    records = row.get("records") if isinstance(row.get("records"), list) else row.get("record") if isinstance(row.get("record"), list) else []
    record = None
    for entry in records:
        if isinstance(entry, Mapping) and entry.get("summary"):
            record = str(entry["summary"])
            break
    return {
        "team": _text(team.get("displayName")) or _text(team.get("name")),
        "short": _text(team.get("shortDisplayName")),
        "abbrev": _text(team.get("abbreviation")),
        "location": _text(team.get("location")),
        "nickname": _text(team.get("name")),
        "id": _text(team.get("id")),
        "score": _int(row.get("score")),
        "winner": row.get("winner") if isinstance(row.get("winner"), bool) else None,
        "record": record,
    }


def _odds(row: Any, home_abbrev: "str | None") -> "dict[str, Any] | None":
    """One `odds[0]` (scoreboard) or `pickcenter[0]` (summary) entry as the home-signed line."""
    if not isinstance(row, Mapping):
        return None
    home = row.get("homeTeamOdds") if isinstance(row.get("homeTeamOdds"), Mapping) else {}
    away = row.get("awayTeamOdds") if isinstance(row.get("awayTeamOdds"), Mapping) else {}
    spread = _float(row.get("spread"))
    details = _text(row.get("details"))
    if spread is not None:
        if home.get("favorite") is True:
            spread = -abs(spread)
        elif away.get("favorite") is True:
            spread = abs(spread)
        elif details and home_abbrev and details.upper().startswith(home_abbrev.upper() + " "):
            spread = -abs(spread)
    moneyline = row.get("moneyline") if isinstance(row.get("moneyline"), Mapping) else {}

    def closing(side: str) -> "int | None":
        leg = moneyline.get(side)
        close = leg.get("close") if isinstance(leg, Mapping) else None
        return _moneyline(close.get("odds")) if isinstance(close, Mapping) else None

    provider = row.get("provider") if isinstance(row.get("provider"), Mapping) else {}
    return {
        "details": details,
        "spread": spread,
        "over_under": _float(row.get("overUnder")),
        "home_ml": closing("home") if closing("home") is not None else _moneyline(home.get("moneyLine")),
        "away_ml": closing("away") if closing("away") is not None else _moneyline(away.get("moneyLine")),
        "provider": _text(provider.get("name")),
    }


def event_row(event: Any) -> "dict[str, Any] | None":
    """One scoreboard event (or a summary `header`) reduced to a flat row, or None if unusable."""
    if not isinstance(event, Mapping):
        return None
    competitions = event.get("competitions")
    competition = competitions[0] if isinstance(competitions, list) and competitions and isinstance(competitions[0], Mapping) else None
    event_id = _text(event.get("id")) or (_text(competition.get("id")) if competition else None)
    if competition is None or event_id is None:
        return None
    home = away = None
    for raw in competition.get("competitors") if isinstance(competition.get("competitors"), list) else []:
        side = _competitor(raw)
        if side is None:
            continue
        if str(raw.get("homeAway")) == "home":
            home = side
        elif str(raw.get("homeAway")) == "away":
            away = side
    status = competition.get("status") if isinstance(competition.get("status"), Mapping) else event.get("status") if isinstance(event.get("status"), Mapping) else {}
    kind = status.get("type") if isinstance(status.get("type"), Mapping) else {}
    odds_rows = competition.get("odds")
    name = _text(event.get("name"))
    if name is None and home and away:
        name = f"{away.get('team')} at {home.get('team')}"
    start = _text(event.get("date")) or _text(competition.get("date"))
    try:
        start = iso(start) if start else None
    except DataError:
        pass
    return {
        "id": event_id,
        "name": name,
        "short_name": _text(event.get("shortName")),
        "start": start,
        "status": _text(kind.get("state")) or "pre",
        "detail": _text(kind.get("shortDetail")) or _text(kind.get("detail")),
        "completed": bool(kind.get("completed", False)),
        "period": _int(status.get("period")),
        "clock": _text(status.get("displayClock")),
        "home": home,
        "away": away,
        "odds": _odds(odds_rows[0], home.get("abbrev") if home else None) if isinstance(odds_rows, list) and odds_rows else None,
    }


def _athlete(row: Any) -> "dict[str, Any] | None":
    """One side of an individual sport's bout (MMA): the athlete's names where a team's would be,
    with the same keys (`abbrev`, `location` and `nickname` None) and `id` the athlete's ESPN id."""
    if not isinstance(row, Mapping) or not isinstance(row.get("athlete"), Mapping):
        return None
    athlete = row["athlete"]
    record = next((str(entry["summary"]) for entry in row.get("records") or [] if isinstance(entry, Mapping) and entry.get("summary")), None)
    return {
        "team": _text(athlete.get("displayName")) or _text(athlete.get("fullName")),
        "short": _text(athlete.get("shortName")),
        "abbrev": None,
        "location": None,
        "nickname": None,
        "id": _text(row.get("id")) or _text(athlete.get("id")),
        "score": _int(row.get("score")),
        "winner": row.get("winner") if isinstance(row.get("winner"), bool) else None,
        "record": record,
    }


def _is_card(event: Any) -> bool:
    """Is this event a card of bouts between two athletes (an MMA event), not one game of two teams?"""
    competitions = event.get("competitions") if isinstance(event, Mapping) else None
    for competition in competitions if isinstance(competitions, list) else []:
        competitors = competition.get("competitors") if isinstance(competition, Mapping) else None
        if isinstance(competitors, list) and len(competitors) == 2 and all(
                isinstance(c, Mapping) and isinstance(c.get("athlete"), Mapping) and not isinstance(c.get("team"), Mapping) for c in competitors):
            return True
    return False


def bout_rows(event: Any) -> "list[dict[str, Any]]":
    """A card (an MMA event: one competition a bout, two athletes each; probed Sept 25, 2026) as ONE
    ROW A BOUT, in the shape `event_row` gives a game: `id` is the bout's (the competition's) id, and
    `card_id` / `card` name the event it is on (ESPN's core API wants both for the bout's odds). Each
    bout carries its own start (a card's prelims and main card start at different times) and status.
    ESPN's MMA competitors have no homeAway; `order` 1 is `home` and 2 `away`, which is how the core
    API's odds name them (`homeAthleteOdds` was the order-1 athlete on all ten bouts it priced that
    day). A bout that is not two athletes, one of each order, is left out."""
    if not isinstance(event, Mapping):
        return []
    card_id, card = _text(event.get("id")), _text(event.get("name"))
    rows = []
    for competition in event.get("competitions") if isinstance(event.get("competitions"), list) else []:
        if not isinstance(competition, Mapping) or _text(competition.get("id")) is None:
            continue
        sides: dict[str, Any] = {}
        for raw in competition.get("competitors") if isinstance(competition.get("competitors"), list) else []:
            side = _athlete(raw)
            where = str(raw.get("homeAway") or "") or {1: "home", 2: "away"}.get(_int(raw.get("order")) or 0, "") if side else ""
            if where in ("home", "away") and where not in sides:
                sides[where] = side
            else:
                sides["?"] = side
        if set(sides) != {"home", "away"}:
            continue
        status = competition.get("status") if isinstance(competition.get("status"), Mapping) else {}
        kind = status.get("type") if isinstance(status.get("type"), Mapping) else {}
        start = _text(competition.get("date")) or _text(competition.get("startDate")) or _text(event.get("date"))
        try:
            start = iso(start) if start else None
        except DataError:
            pass
        weight = competition.get("type") if isinstance(competition.get("type"), Mapping) else {}
        rows.append({
            "id": _text(competition.get("id")),
            "card_id": card_id,
            "card": card,
            "name": f"{sides['home'].get('team')} vs {sides['away'].get('team')}",
            "short_name": _text(weight.get("abbreviation")),
            "start": start,
            "status": _text(kind.get("state")) or "pre",
            "detail": _text(kind.get("shortDetail")) or _text(kind.get("detail")),
            "completed": bool(kind.get("completed", False)),
            "period": _int(status.get("period")),
            "clock": _text(status.get("displayClock")),
            "home": sides["home"],
            "away": sides["away"],
            "odds": None,
        })
    return rows


def event_rows(event: Any) -> "list[dict[str, Any]]":
    """One scoreboard event as the rows a board lists: a card of bouts is a row a bout (`bout_rows`),
    any other event its one `event_row` (none when unusable)."""
    if _is_card(event):
        return bout_rows(event)
    row = event_row(event)
    return [row] if row is not None else []


def _last_play(payload: Mapping[str, Any]) -> "str | None":
    """The most recent play's text from a summary, whichever shape the sport uses."""
    candidates: list[Any] = []
    drives = payload.get("drives")
    if isinstance(drives, Mapping):
        current = drives.get("current")
        if isinstance(current, Mapping) and isinstance(current.get("plays"), list):
            candidates.extend(current["plays"])
        previous = drives.get("previous")
        if isinstance(previous, list) and not candidates:
            for drive in previous:
                if isinstance(drive, Mapping) and isinstance(drive.get("plays"), list):
                    candidates = list(drive["plays"])  # the last drive with plays wins
    if not candidates and isinstance(payload.get("plays"), list):
        candidates = list(payload["plays"])
    for play in reversed(candidates):
        if isinstance(play, Mapping) and _text(play.get("text")):
            return str(play["text"])
    return None


def _american(value: Any) -> "int | None":
    """An American price from the core API: an int, or a dict carrying `american` ("-360", "+280")."""
    if isinstance(value, Mapping):
        value = value.get("american")
    return _moneyline(value)


def implied_home(home_ml: "int | None", away_ml: "int | None") -> "float | None":
    """The home side's win probability the two moneylines imply once the book's margin is taken out
    (each price's implied probability, over their sum). None unless both are there."""
    def raw(price: "int | None") -> "float | None":
        if price is None or price == 0:
            return None
        return 100.0 / (price + 100.0) if price > 0 else -price / (-price + 100.0)

    home, away = raw(home_ml), raw(away_ml)
    return round(home / (home + away), 4) if home is not None and away is not None and home + away > 0 else None


def implied(*prices: "int | None") -> "list[float] | None":
    """The probabilities a set of American prices (two sides, or three with a draw) imply once the
    book's margin is taken out: each price's implied probability over their sum. None unless every
    price is there."""
    raw = []
    for price in prices:
        if price is None or price == 0:
            return None
        raw.append(100.0 / (price + 100.0) if price > 0 else -price / (-price + 100.0))
    total = sum(raw)
    return [round(value / total, 4) for value in raw] if total > 0 else None


def _spread_price(side: Mapping[str, Any]) -> "int | None":
    """One side's price on the spread: `spreadOdds`, or (baseball's run line) `current.spread`."""
    price = _american(side.get("spreadOdds"))
    if price is None:
        current = side.get("current") if isinstance(side.get("current"), Mapping) else {}
        price = _american(current.get("spread"))
    return price


def _athlete_id(side: Mapping[str, Any]) -> "str | None":
    """The ESPN id of the athlete one side of a bout's odds names (`athlete.$ref` ends `/athletes/<id>?...`)."""
    ref = side.get("athlete").get("$ref") if isinstance(side.get("athlete"), Mapping) else None
    found = re.search(r"/athletes/(\d+)", ref) if isinstance(ref, str) else None
    return found.group(1) if found else None


def parse_core_odds(payload: Any) -> "list[dict[str, Any]]":
    """The core API's odds of one competition as one row per provider, best priority first:
    `{provider, details, spread, over_under, home_ml, away_ml, implied_home, open: {spread, home_ml,
    away_ml}}` -- spreads signed from the home side, moneylines American, `implied_home` de-vigged --
    and since Sept 25, 2026: `draw_ml` (soccer's draw price, else None), `implied_away` and
    `implied_draw` (with a draw price the three are the THREE-way de-vig and sum to 1; without one
    `implied_draw` is None and the two sides' are the two-way de-vig, as `implied_home` always was),
    `over_odds` / `under_odds` and `implied_over` (the total's prices, de-vigged: the chance the game
    goes over `over_under`), `home_spread_odds` / `away_spread_odds` and `implied_home_cover` (the
    chance the home side covers `spread`). An individual sport's bout (MMA, Sept 25, 2026) prices each
    ATHLETE (`homeAthleteOdds` / `awayAthleteOdds`): its row is the same, plus `home_athlete` and
    `away_athlete`, the ESPN ids of the athletes the home and away prices are for."""
    items = payload.get("items") if isinstance(payload, Mapping) else None
    require(isinstance(items, list), "espn core odds: no items")
    out = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        home = item.get("homeTeamOdds") if isinstance(item.get("homeTeamOdds"), Mapping) else {}
        away = item.get("awayTeamOdds") if isinstance(item.get("awayTeamOdds"), Mapping) else {}
        athletes = not home and not away and isinstance(item.get("homeAthleteOdds"), Mapping) and isinstance(item.get("awayAthleteOdds"), Mapping)
        if athletes:  # an individual sport's bout (MMA): the same prices, under each athlete
            home, away = item["homeAthleteOdds"], item["awayAthleteOdds"]
        provider = item.get("provider") if isinstance(item.get("provider"), Mapping) else {}
        opened_home = home.get("open") if isinstance(home.get("open"), Mapping) else {}
        opened_away = away.get("open") if isinstance(away.get("open"), Mapping) else {}
        home_ml, away_ml = _american(home.get("moneyLine")), _american(away.get("moneyLine"))
        draw = item.get("drawOdds") if isinstance(item.get("drawOdds"), Mapping) else {}
        draw_ml = _american(draw.get("moneyLine"))
        spread = opened_home.get("pointSpread") if isinstance(opened_home.get("pointSpread"), Mapping) else {}
        current = item.get("current") if isinstance(item.get("current"), Mapping) else {}
        over_odds = _american(item.get("overOdds"))
        under_odds = _american(item.get("underOdds"))
        if over_odds is None and under_odds is None:
            over_odds, under_odds = _american(current.get("over")), _american(current.get("under"))
        home_spread, away_spread = _spread_price(home), _spread_price(away)
        sides = implied(home_ml, away_ml, draw_ml) if draw_ml is not None else implied(home_ml, away_ml)
        over = implied(over_odds, under_odds)
        cover = implied(home_spread, away_spread)
        out.append({
            "provider": _text(provider.get("name")),
            "priority": _int(provider.get("priority")),
            "details": _text(item.get("details")),
            "spread": _float(item.get("spread")),
            "over_under": _float(item.get("overUnder")),
            "home_ml": home_ml,
            "away_ml": away_ml,
            "draw_ml": draw_ml,
            "implied_home": sides[0] if sides else None,
            "implied_away": sides[1] if sides else None,
            "implied_draw": sides[2] if sides and draw_ml is not None else None,
            "over_odds": over_odds,
            "under_odds": under_odds,
            "implied_over": over[0] if over else None,
            "home_spread_odds": home_spread,
            "away_spread_odds": away_spread,
            "implied_home_cover": cover[0] if cover else None,
            "open": {"spread": _float(str(spread.get("american") or "").replace("+", "") or None),
                     "home_ml": _american(opened_home.get("moneyLine")), "away_ml": _american(opened_away.get("moneyLine"))},
        })
        if athletes:
            out[-1]["home_athlete"], out[-1]["away_athlete"] = _athlete_id(home), _athlete_id(away)
    out.sort(key=lambda row: (row["priority"] is None, row["priority"] or 0))
    return out


def parse_predictor(payload: Any) -> "dict[str, Any] | None":
    """The matchup predictor's win probability of one competition, `{home, away, tie, modified}` as
    fractions, or None when it carries no projection."""
    if not isinstance(payload, Mapping):
        return None

    def stat(side: str, name: str) -> "float | None":
        team = payload.get(side) if isinstance(payload.get(side), Mapping) else {}
        for row in team.get("statistics") if isinstance(team.get("statistics"), list) else []:
            if isinstance(row, Mapping) and row.get("name") == name:
                return _float(row.get("value"))
        return None

    home, away = stat("homeTeam", "gameProjection"), stat("awayTeam", "gameProjection")
    if home is None or away is None:
        return None
    tie = stat("homeTeam", "teamChanceTie")
    return {"home": round(home / 100.0, 5), "away": round(away / 100.0, 5), "tie": round(tie / 100.0, 5) if tie is not None else None,
            "modified": _text(payload.get("lastModified"))}


class Sports:
    """League scoreboards and one game's summary, reduced to flat rows."""

    source = SOURCE

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        cache_dir: Any = None,
        cache_ttl: float = 30.0,
        clock: Any = time.time,
    ):
        self.transport = transport or HttpTransport(
            cache_dir=cache_dir, ttl=cache_ttl, user_agent=USER_AGENT, min_interval=MIN_INTERVAL
        )
        self.timeout = float(timeout)
        self.clock = clock

    def _get(self, url: str, what: str) -> Mapping[str, Any]:
        payload = read_json(
            self.transport,
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=self.timeout,
            what=what,
        )
        require(isinstance(payload, Mapping), f"{what}: not an object")
        return payload

    def scoreboard(self, league: str, query: str = "") -> list[dict[str, Any]]:
        """Every game on the league's current scoreboard, in ESPN's order (`board`'s events)."""
        return self.board(league, query)["events"]

    def board(self, league: str, query: str = "") -> dict[str, Any]:
        """One scoreboard read: `{"events": [...], "day": "YYYY-MM-DD" | None}`. `query` is the site
        API's query string as is (`groups=80&limit=300`, `dates=20260926`); `day` is the one day a
        daily league's board shows (ESPN's `day.date`), None on a weekly board (football)."""
        path = league_path(league)
        url = f"{HOST}/apis/site/v2/sports/{path}/scoreboard" + (f"?{query}" if query else "")
        payload = self._get(url, f"espn scoreboard {league}" + (f" ({query})" if query else ""))
        events = payload.get("events")
        require(isinstance(events, list), f"espn scoreboard {league}: no events list")
        day = payload.get("day") if isinstance(payload.get("day"), Mapping) else {}
        # A card of bouts (MMA) is a row a bout (`event_rows`); every other event its one row, as before.
        return {"events": [row for event in events for row in event_rows(event)], "day": _text(day.get("date"))}

    def game(self, league: str, event_id: Any) -> dict[str, Any]:
        """One game's summary as a scoreboard row plus `last_play`, `win_probability`, `predictor`."""
        path = league_path(league)
        event_id = str(event_id or "").strip()
        require(event_id, "espn game: empty event id")
        payload = self._get(f"{HOST}/apis/site/v2/sports/{path}/summary?event={event_id}", f"espn game {event_id}")
        header = payload.get("header")
        row = event_row(header) if isinstance(header, Mapping) else None
        require(row is not None, f"espn game {event_id}: no header")
        if row["odds"] is None:
            picks = payload.get("pickcenter")
            if isinstance(picks, list) and picks:
                row["odds"] = _odds(picks[0], row["home"].get("abbrev") if row["home"] else None)
        row["last_play"] = _last_play(payload)
        row["win_probability"] = None
        probabilities = payload.get("winprobability")
        if isinstance(probabilities, list) and probabilities and isinstance(probabilities[-1], Mapping):
            home = _float(probabilities[-1].get("homeWinPercentage"))
            tie = _float(probabilities[-1].get("tiePercentage")) or 0.0
            if home is not None:
                row["win_probability"] = {"home": round(home, 4), "away": round(max(0.0, 1.0 - home - tie), 4), "tie": round(tie, 4)}
        row["predictor"] = None
        predictor = payload.get("predictor")
        if isinstance(predictor, Mapping):
            home_team = predictor.get("homeTeam") if isinstance(predictor.get("homeTeam"), Mapping) else {}
            away_team = predictor.get("awayTeam") if isinstance(predictor.get("awayTeam"), Mapping) else {}
            home_pct, away_pct = _float(home_team.get("gameProjection")), _float(away_team.get("gameProjection"))
            if home_pct is not None or away_pct is not None:
                row["predictor"] = {"home": home_pct, "away": away_pct}
        row["as_of"] = iso(float(self.clock()))
        return row

    def core_odds(self, league: str, event_id: Any, card: Any = None) -> "list[dict[str, Any]]":
        """Every provider's line of one game from ESPN's core API (`parse_core_odds`). A bout of a card
        (MMA: `bout_rows`) is asked by its card's id and its own (`card`): ESPN answers 404 for the
        bout's id alone, which would read as no line at all (probed Sept 25, 2026)."""
        sport, _, code = league_path(league).partition("/")
        event = str(event_id or "").strip()
        require(event.isdigit(), f"espn core odds: not an event id {event_id!r}")
        parent = str(card).strip() if card not in (None, "") else event
        require(parent.isdigit(), f"espn core odds: not a card id {card!r}")
        url = f"{CORE_HOST}/v2/sports/{sport}/leagues/{code}/events/{parent}/competitions/{event}/odds"
        status, _, body = self.transport.get(url, {"Accept": "application/json", "User-Agent": USER_AGENT}, self.timeout)
        if status == 404:
            return []  # no book lists a line for this game: none shown, not a failure
        if status != 200:
            raise DataError(f"espn core odds {event}: HTTP {status} from {url}")
        try:
            import json

            return parse_core_odds(json.loads(body.decode("utf-8")))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DataError(f"espn core odds {event}: malformed JSON") from exc

    def core_predictor(self, league: str, event_id: Any) -> "dict[str, Any] | None":
        """The matchup predictor's win probability of one game, or None where ESPN has none (it
        answers 404 outside football and basketball)."""
        sport, _, code = league_path(league).partition("/")
        event = str(event_id or "").strip()
        require(event.isdigit(), f"espn predictor: not an event id {event_id!r}")
        url = f"{CORE_HOST}/v2/sports/{sport}/leagues/{code}/events/{event}/competitions/{event}/predictor"
        status, _, body = self.transport.get(url, {"Accept": "application/json", "User-Agent": USER_AGENT}, self.timeout)
        if status == 404:
            return None
        if status != 200:
            raise DataError(f"espn predictor {event}: HTTP {status} from {url}")
        try:
            import json

            return parse_predictor(json.loads(body.decode("utf-8")))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DataError(f"espn predictor {event}: malformed JSON") from exc

    @staticmethod
    def match_kalshi(title: str, rows: list[dict[str, Any]]) -> "dict[str, Any] | None":
        """The scoreboard row a Kalshi title names, with `side` (home|away) for the team named first.

        "Will the Chiefs beat the Ravens?" matches the row whose teams include Chiefs and Ravens
        and sets side to whichever of home/away the Chiefs are. Team nicknames, locations,
        full names and abbreviations all count; the row with the most matched teams wins."""
        haystack = " " + " ".join(_TOKEN.findall(str(title or "").lower())) + " "
        best: "tuple[int, int, dict[str, Any], str] | None" = None
        for row in rows or []:
            if not isinstance(row, Mapping):
                continue
            matched = 0
            first_side, first_position = None, len(haystack)
            for side in ("home", "away"):
                team = row.get(side)
                if not isinstance(team, Mapping):
                    continue
                position = _team_position(team, haystack)
                if position is None:
                    continue
                matched += 1
                if position < first_position:
                    first_side, first_position = side, position
            if matched and first_side and (best is None or (matched, -first_position) > (best[0], -best[1])):
                best = (matched, first_position, dict(row), first_side)
        if best is None:
            return None
        found = best[2]
        found["side"] = best[3]
        found["side_team"] = (found.get(best[3]) or {}).get("team")
        found["matched_teams"] = best[0]
        return found


def _team_position(team: Mapping[str, Any], haystack: str) -> "int | None":
    """Where the team is first named in the tokenized title, or None if it is not."""
    names = []
    for key in ("team", "nickname", "location"):
        value = team.get(key)
        if isinstance(value, str) and len(value) >= 3:
            names.append(" ".join(_TOKEN.findall(value.lower())))
    abbrev = team.get("abbrev")
    if isinstance(abbrev, str) and len(abbrev) >= 2:
        names.append(abbrev.lower())
    positions = [haystack.find(" " + name + " ") for name in names if name]
    hits = [p for p in positions if p >= 0]
    return min(hits) if hits else None


__all__ = ["CORE_HOST", "HOST", "LEAGUES", "Sports", "USER_AGENT", "bout_rows", "event_row", "event_rows", "implied", "implied_home",
           "league_path", "parse_core_odds", "parse_predictor"]
