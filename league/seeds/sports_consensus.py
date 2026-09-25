# sports-consensus: price Kalshi game markets (who wins, by how much, how many points) from the
# sportsbook line the House records, and bid where Kalshi is off it by more than fees and a margin.
#
# THE IDEA. A sportsbook's closing line is the best public forecast of a game there is: millions
# of dollars of sharp money set it, and the book's margin can be taken out of its two (or three)
# prices. Kalshi lists the same games as binary contracts, often thinly, and its prices lag the
# book's. Where a Kalshi contract trades below the book's de-vigged probability by more than the
# fee and a margin, a resting maker bid there is a bet the book is right and Kalshi is late.
#
# THE EVIDENCE. UNMEASURED as a strategy: the sportsbook line as a second price is published
# folklore (closing lines beat almost every model), and the House only began recording the lines on
# Sept 24, 2026 (league/feeds.py `odds`), so there is no replay: practice is the test. What IS
# measured is the premise, and it is thin. Every recorded `odds` row's DraftKings de-vigged win
# probability against Kalshi's winner-market prints in the 30 minutes before it (Sept 24 08:35Z to
# Sept 25 06:30Z): MLB 112 readings on 10 games, Kalshi minus the book +0.6 cents on average,
# median gap 0.7c, 90th percentile 1.4c, none of 3c or more; WNBA 56 on 4 games, median 1.3c, p90
# 2.2c; NCAAF 6 on 4 games, median 1.8c, p90 2.7c. On WINNERS Kalshi sits on the book's line, so
# a winner is bid inside the spread at a small edge (min_edge_winner, about a cent after the maker
# fee) and adverse selection is the risk to manage: a bid is withdrawn as soon as the line moves.
# The spread and total ladders are thinner and wider and the model's error there is larger, so
# they ask more (min_edge_ladder). Takers only at take_edge, which on winners almost never fires.
# ESPN's core API carried ONE book (DraftKings) for every NFL, NCAAF, MLB and MLS game probed on
# Sept 25, so "consensus" is one book's line until more appear; the mean over providers is taken
# whenever there are several.
#
# WHAT IT NEEDS. The league's Kalshi game series (GAME, SPREAD, TOTAL), the `odds` feed (every
# provider's line for the coming games, with when each was fetched) and the `sports` scoreboard (the
# teams' ESPN abbreviations and names, and each game's status and start). Woken every ten minutes.
#
# HOW A MARKET IS MATCHED TO A GAME, WITHOUT GUESSING. A Kalshi ticker names its game:
# KXNFLSPREAD-26OCT01PITCLE-PIT8 is the Oct 1 game of PIT and CLE (dates are New York dates;
# baseball adds the first pitch, 26SEP251805CHCBOSG2, and a doubleheader's game number). A market
# is priced only when exactly one game on the scoreboard has that New York date (and first pitch)
# and its two teams are exactly the two codes the ticker spells, in either order: a code is a team
# when it IS its ESPN abbreviation, a known Kalshi spelling of it (JAC for JAX), or when a market of
# the same game titles that code with the team's own name ("Northwestern wins" on -NW). Anything
# else -- no game, two games, a code that fits both teams -- is skipped, never guessed.
#
# FAIR VALUE. Winner: the mean over providers of the de-vigged win probability (a three-way
# de-vig with the draw for soccer), optionally blended with ESPN's predictor. Spread "X wins by
# over s": X's margin ~ Normal(mu, sigma_margin), mu from the spread line and its juice (home -7 at
# even money: the home side is expected to win by 7); the game is skipped when that model's win
# probability and the moneyline's disagree by more than ml_tolerance. Total "over s": Normal(mu,
# sigma_total), mu the line moved by its over/under juice. Only strikes within max_strike_z sigmas
# of the line are priced: the book's line says most about the strikes near it. Football margins are
# lumpy at the KEY numbers (3 and 7 above all: a 7-point favourite wins by exactly 3 far more often
# than a normal curve says), so a football spread strike is priced only when no key number lies
# between it and the book's line, an integer line on a key number (a push) included. Baseball margins
# are not normal either (a third of games are decided by one run), so a baseball spread is priced
# only at the book's own run line, from its de-vigged run-line price. Soccer: only the winner and
# the tie.
#
# WHEN IT TRADES. Only games that have not started, start more than start_buffer_minutes from now,
# and whose lines were fetched within stale_minutes. It buys YES or NO -- never both, and at most
# one market an event (a ticker's first two segments) and max_per_game markets a game -- as a
# post-only maker bid at most fair - min_edge - the maker fee a contract (min_edge_winner on a
# winner, min_edge_ladder on a spread or total), one tick over the best bid where that still clears
# the edge, else at the bid; it takes the ask (a limit at the ask, not post-only) only when the edge
# after the TAKER fee is at least take_edge, and never on a book that has refused its taker entry.
# Fees as the book charges them (ltcm/sim.py `kalshi_fee`): taker 0.07 x C x P x (1 - P) on the order,
# rounded up to $0.0001; a maker pays a quarter of that on the series Kalshi charges makers (the
# desk's `maker_fee_series`), nothing elsewhere. Kalshi also scales both by a series multiplier
# (GET /series, Sept 25, 2026: 1 on every NFL, NCAAF, MLS and Liga MX series, 0.5 on KXMLBGAME,
# KXMLBSPREAD and KXMLBTOTAL; makers pay on KXMLBGAME only of the three). ctx["fees"] carries no
# multiplier, so the price is the full rate (fee_multiplier 1.0, bounded down to the measured 0.5).
#
# HOW IT EXITS. It does not sell: a contract is held to settlement. A resting bid is cancelled when
# its game is within start_buffer_minutes of the start, when the fair has moved requote_move or more
# since the bid was priced (the fair is kept in memory, by market), when its edge at the current
# fair falls under half its min_edge, when the line can no longer be read fresh, or after
# requote_minutes when a better price is due.

from datetime import datetime, timedelta, timezone
from statistics import NormalDist
import math
import re

NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "model-versus-market",
    "series": ["KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL"],
    "max_hours_to_close": 30,
    "wake_minutes": 10,
    "feeds": {"odds": ["nfl"], "sports": ["nfl"]},
    "parameter_rules": {
        "bounds": {
            "min_edge_winner": [0.005, 0.08],
            "min_edge_ladder": [0.01, 0.12],
            "take_edge": [0.04, 0.25],
            "requote_move": [0.005, 0.05],
            "ticket_usd": [1.0, 50.0],
            "max_new": [1, 6],
            "max_per_game": [1, 3],
            "start_buffer_minutes": [10, 120],
            "stale_minutes": [30, 240],
            "requote_minutes": [10, 240],
            "sigma_margin": [3.0, 22.0],
            "sigma_total": [3.0, 22.0],
            "max_strike_z": [0.1, 1.5],
            "ml_tolerance": [0.02, 0.2],
            "predictor_weight": [0.0, 0.5],
            "min_price": [0.05, 0.5],
            "max_price": [0.5, 0.97],
            "fee_multiplier": [0.5, 1.0],
        },
        "ordered": [["min_edge_winner", "take_edge"], ["min_edge_ladder", "take_edge"], ["min_price", "max_price"]],
    },
}
PARAMS = {
    "min_edge_winner": 0.012,
    "min_edge_ladder": 0.03,
    "take_edge": 0.06,
    "requote_move": 0.01,
    "ticket_usd": 10.0,
    "max_new": 3,
    "max_per_game": 1,
    "start_buffer_minutes": 20,
    "stale_minutes": 90,
    "requote_minutes": 60,
    "sigma_margin": 13.5,
    "sigma_total": 13.5,
    "max_strike_z": 0.5,
    "ml_tolerance": 0.08,
    "predictor_weight": 0.0,
    "min_price": 0.15,
    "max_price": 0.9,
    "fee_multiplier": 1.0,
}

TICK = 0.01
EPS = 1e-9
TAKER_RATE = 0.07
MAKER_SHARE = 0.25  # a maker pays a quarter of the taker rate on the series that charge makers
# The series of the sports desk that charge makers (its `maker_fee_series` in league/niches.json, the
# schedule the book charges by: ltcm/data/kalshi_fees.json), those this program can trade.
MAKER_FEE_SERIES = ("KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL", "KXNCAAFGAME", "KXNCAAFSPREAD", "KXNCAAFTOTAL",
                    "KXMLBGAME", "KXEPLGAME", "KXLALIGAGAME", "KXSERIEAGAME", "KXBUNDESLIGAGAME", "KXLIGUE1GAME",
                    "KXWNBAGAME", "KXNHLGAME", "KXNBAGAME", "KXNBASPREAD", "KXNBATOTAL")
MAX_EVENT_SHARE = 0.25  # allocator.max_event_share: one event holds at most a quarter of the equity
LONGSHOT_FLOOR_REAL = 0.30  # allocator.longshot_floor_real: no real entry under 30 cents
MAX_INTENTS = 8
# Kalshi series prefix -> the league key the House's feeds use, and the kind of game it is.
LEAGUES = (("KXNCAAF", "ncaaf", "football"), ("KXNFL", "nfl", "football"), ("KXMLB", "mlb", "baseball"),
           ("KXMLS", "mls", "soccer"), ("KXLIGAMX", "ligamx", "soccer"), ("KXEPL", "epl", "soccer"),
           ("KXLALIGA", "laliga", "soccer"), ("KXSERIEA", "seriea", "soccer"), ("KXBUNDESLIGA", "bundesliga", "soccer"),
           ("KXLIGUE1", "ligue1", "soccer"), ("KXEFLCHAMPIONSHIP", "championship", "soccer"))
# Kalshi codes that are not ESPN's abbreviation (the live boards of Sept 25, 2026): ESPN -> Kalshi.
ALIASES = {"nfl": {"JAX": ("JAC",), "WSH": ("WAS",)}, "mlb": {"ARI": ("AZ",), "CHW": ("CWS",)}, "ncaaf": {"ALB": ("ALBY",)},
           "mls": {"LA": ("LAG",), "RBNY": ("NYRB",), "DC": ("DCU",)}, "ligamx": {"SAN": ("SLA",), "UANL": ("TIG",)}}
#: A doubleheader's second game is listed at its planned first pitch and moves by minutes (Sept 25,
#: 2026: Kalshi's CHC-BOS game 2 at 6:05 PM, ESPN's at 6:00 PM). Two games of one pair of teams are
#: never this close, so a first pitch within this many minutes is the same game.
CLOCK_MINUTES = 15
#: The margins a football game ends on far more often than a smooth curve says, by league.
KEY_MARGINS = {"nfl": (3, 7, 10, 14), "ncaaf": (3, 7)}
MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10,
          "NOV": 11, "DEC": 12}
EVENT_CODE = re.compile(r"^(\d{2})([A-Z]{3})(\d{2})(\d{4})?([A-Z]+?)(G\d)?$")
GAME_TITLE = re.compile(r"^(.+?) wins\??$")
SPREAD_TITLE = re.compile(r"^(.+?) wins by over (\d+(?:\.\d+)?) (?:points|runs|goals)\??$")
TOTAL_TITLE = re.compile(r"^(?:Full Game: )?[Oo]ver (\d+(?:\.\d+)?) (?:points|runs|goals)(?: scored)?\??$")
ACCENTS = str.maketrans("áàâäãéèêëíìîïóòôöõúùûüñç", "aaaaaeeeeiiiiooooouuuunc")
NORMAL = NormalDist()


def num(value, default=None):
    """A finite float, or the default for anything else (None, text, NaN)."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def when(text):
    """ISO-8601 text as an aware datetime (UTC when it has no offset), or None."""
    try:
        clean = str(text).strip()
        if clean[-1:] in "Zz":
            clean = clean[:-1] + "+00:00"
        moment = datetime.fromisoformat(clean)
    except (TypeError, ValueError, IndexError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def new_york(moment):
    """A UTC moment as New York wall time (US daylight time: 2:00 on the second Sunday of March to
    2:00 on the first Sunday of November), without relying on a time-zone database in the box."""
    utc = moment.astimezone(timezone.utc)
    march = datetime(utc.year, 3, 8, 7, tzinfo=timezone.utc)
    november = datetime(utc.year, 11, 1, 6, tzinfo=timezone.utc)
    begins = march + timedelta(days=(6 - march.weekday()) % 7)
    ends = november + timedelta(days=(6 - november.weekday()) % 7)
    return utc + timedelta(hours=-4 if begins <= utc < ends else -5)


def words(text):
    """A team name reduced for comparison: lower case, accents and punctuation out, `St.` at the end
    read as State (Kalshi's "Arkansas St." is ESPN's "Arkansas State") and at the start as Saint."""
    tokens = re.findall(r"[a-z0-9&]+", re.sub(r"[.'\u2019]", "", str(text or "").lower().translate(ACCENTS)))
    if len(tokens) > 1 and tokens[-1] == "st":
        tokens[-1] = "state"
    if len(tokens) > 1 and tokens[0] == "st":
        tokens[0] = "saint"
    return " ".join(tokens)


def league_of(series):
    for prefix, league, sport in LEAGUES:
        if series.startswith(prefix):
            return league, sport
    return None, None


def kind_of(series):
    for kind in ("SPREAD", "TOTAL", "GAME"):
        if series.endswith(kind):
            prefix = series[: -len(kind)]
            return kind if any(prefix == p for p, _, _ in LEAGUES) else None
    return None


def parse_market(row):
    """What the ticker and title say: series, kind, league, the game's key, date, first pitch,
    the two teams' codes run together, the market's own team code and its line. None if unreadable."""
    ticker = str(row.get("market") or "").upper()
    parts = ticker.split("-")
    if len(parts) != 3:
        return None
    series, code, suffix = parts
    kind = kind_of(series)
    league, sport = league_of(series)
    found = EVENT_CODE.match(code)
    if kind is None or found is None or found.group(2) not in MONTHS:
        return None
    title = str(row.get("title") or "").strip()
    out = {"ticker": ticker, "series": series, "kind": kind, "league": league, "sport": sport,
           "event": series + "-" + code, "game": league + ":" + code,
           "date": (2000 + int(found.group(1)), MONTHS[found.group(2)], int(found.group(3))),
           "clock": found.group(4), "teams": found.group(5), "team": None, "name": None, "line": None}
    strike = num(row.get("strike"))
    if kind == "GAME":
        if suffix == "TIE":
            out["team"] = "TIE"
            return out if sport == "soccer" else None
        said = GAME_TITLE.match(title)
        out["team"], out["name"] = suffix, said.group(1) if said else None
        return out
    if kind == "SPREAD":
        said = SPREAD_TITLE.match(title)
        team = re.match(r"^([A-Z]+)(\d+)$", suffix)
        if said is None or team is None:
            return None
        out["team"], out["name"], out["line"] = team.group(1), said.group(1), float(said.group(2))
    else:
        said = TOTAL_TITLE.match(title)
        if said is None or not suffix.isdigit():
            return None
        out["line"] = float(said.group(1))
    if strike is not None and abs(strike - out["line"]) > 1e-6:
        return None  # the title and the House's strike disagree: not read
    return out


def team_names(team):
    names = {words(team.get(key)) for key in ("team", "location", "short") if team.get(key)}
    if team.get("abbrev") and team.get("nickname"):
        names.add(words(str(team["abbrev"]) + " " + str(team["nickname"])))  # "PIT Steelers"
    return {name for name in names if name}


def prepare(board):
    """The scoreboard read once a wake: each game with its New York date and first pitch (minutes),
    and each side's abbreviation and names, indexed by date."""
    by_date = {}
    for event in board:
        start = when(event.get("start"))
        home, away = event.get("home"), event.get("away")
        if start is None or not isinstance(home, dict) or not isinstance(away, dict):
            continue
        local = new_york(start)
        sides = {side: (str(team.get("abbrev") or "").upper(), team_names(team)) for side, team in (("home", home), ("away", away))}
        by_date.setdefault((local.year, local.month, local.day), []).append((event, local.hour * 60 + local.minute, sides))
    return by_date


def codes_of(side, league, learned):
    """The Kalshi codes that are this side of a game ((abbreviation, names)): its abbreviation, a known
    Kalshi spelling of it, and any code a title of the same game names with one of the side's names."""
    abbrev, names = side
    return {abbrev, *(ALIASES.get(league) or {}).get(abbrev, ())} | {code for code, said in learned.items() if said & names}


def match_game(parsed, prepared, learned):
    """The one scoreboard game this parsed market is about, as (event, {code: "home"|"away"}), or None:
    the ticker's teams must read as exactly one code of each side, in either order, on exactly one game."""
    found = []
    teams = parsed["teams"]
    for event, minutes, sides in prepared.get(parsed["date"]) or []:
        if parsed["clock"] and abs(minutes - int(parsed["clock"][:2]) * 60 - int(parsed["clock"][2:])) > CLOCK_MINUTES:
            continue
        codes = {name: codes_of(sides[name], parsed["league"], learned) for name in ("home", "away")}
        for first in codes["home"] | codes["away"]:
            second = teams[len(first):] if first and teams.startswith(first) else ""
            if not second:
                continue
            one = [name for name in ("home", "away") if first in codes[name]]
            other = [name for name in ("home", "away") if second in codes[name]]
            if len(one) == 1 and len(other) == 1 and one != other:
                found.append((event, {first: one[0], second: other[0]}))
    if len(found) != 1:
        return None  # no game, or more than one reading: skipped, never guessed
    event, codes = found[0]
    if parsed["team"] not in (None, "TIE") and parsed["team"] not in codes:
        return None
    return event, codes


def devig(first, second):
    """Two American prices as the first side's probability once the book's margin is out."""
    def raw(price):
        price = num(price)
        if price is None or price == 0:
            return None
        return 100.0 / (price + 100.0) if price > 0 else -price / (-price + 100.0)

    a, b = raw(first), raw(second)
    return a / (a + b) if a is not None and b is not None and a + b > 0 else None


def mean(values):
    kept = [v for v in values if v is not None]
    return sum(kept) / len(kept) if kept else None


def consensus(game, sport):
    """The book lines of one odds row reduced to what the pricing reads, averaged over providers."""
    lines = [line for line in game.get("lines") or [] if isinstance(line, dict)]
    out = {"books": len(lines)}
    if sport == "soccer":
        three = [line for line in lines if num(line.get("draw_ml")) is not None and num(line.get("implied_draw")) is not None]
        out["home"] = mean([num(line.get("implied_home")) for line in three])
        out["away"] = mean([num(line.get("implied_away")) for line in three])
        out["draw"] = mean([num(line.get("implied_draw")) for line in three])
        return out
    out["home"] = mean([num(line.get("implied_home")) for line in lines if num(line.get("draw_ml")) is None])
    out["spread"] = mean([num(line.get("spread")) for line in lines])
    out["cover"] = mean([num(line.get("implied_home_cover")) if num(line.get("implied_home_cover")) is not None
                         else devig(line.get("home_spread_odds"), line.get("away_spread_odds")) for line in lines])
    out["total"] = mean([num(line.get("over_under")) for line in lines])
    out["over"] = mean([num(line.get("implied_over")) if num(line.get("implied_over")) is not None
                        else devig(line.get("over_odds"), line.get("under_odds")) for line in lines])
    out["details"] = next((str(line.get("details")) for line in lines if line.get("details")), None)
    return out


def z_of(probability):
    return NORMAL.inv_cdf(min(max(probability, 0.001), 0.999)) if probability is not None else 0.0


def game_model(line, event, sport, p):
    """The distributions one game's lines imply, or (None, why) when they cannot be trusted."""
    home_team = event.get("home") or {}
    home = line.get("home")
    wp = event.get("win_probability") if isinstance(event.get("win_probability"), dict) else None
    if sport == "football" and home is not None and wp and num(wp.get("home")) is not None:
        weight = num(p.get("predictor_weight"), 0.0)
        home = (1.0 - weight) * home + weight * num(wp.get("home"))
    model = {"home": home, "away": None if home is None else 1.0 - home, "draw": None, "margin": None, "total": None}
    if sport == "soccer":
        if line.get("draw") is None or line.get("home") is None or line.get("away") is None:
            return None, "no three-way price"
        model.update(home=line["home"], away=line["away"], draw=line["draw"])
        return model, None
    sigma, sigma_total = num(p.get("sigma_margin"), 13.5), num(p.get("sigma_total"), 13.5)
    if line.get("total") is not None:
        model["total"] = (line["total"] + sigma_total * z_of(line.get("over")), sigma_total)
    if sport == "baseball":
        if line.get("spread") is not None and line.get("cover") is not None:
            model["runline"] = (-line["spread"], line["cover"])  # P(home margin > -spread), the book's own
        return model, None
    spread = line.get("spread")
    if spread is None:
        return model, None
    mu = -spread + sigma * z_of(line.get("cover"))
    implied = NORMAL.cdf(mu / sigma)
    if home is not None:
        if abs(implied - home) > num(p.get("ml_tolerance"), 0.08):
            return None, "spread and moneyline disagree"
    else:
        favourite = re.match(r"^([A-Za-z&.]+) -", str(line.get("details") or ""))
        if favourite is None or (favourite.group(1).upper() == str(home_team.get("abbrev") or "").upper()) != (spread < 0):
            return None, "no moneyline and the favourite cannot be read"
    model["margin"] = (mu, sigma)
    model["line"] = -spread  # the home side's margin the book's line names
    return model, None


def fair_yes(parsed, sides, model, p):
    """The fair price of this market's YES, or None where the model says nothing trustworthy."""
    kind = parsed["kind"]
    if kind == "GAME":
        if parsed["team"] == "TIE":
            return model.get("draw")
        return model.get(sides[parsed["team"]])
    if kind == "TOTAL":
        if model.get("total") is None:
            return None
        mu, sigma = model["total"]
        if abs(parsed["line"] - mu) > num(p.get("max_strike_z"), PARAMS["max_strike_z"]) * sigma:
            return None
        return 1.0 - NORMAL.cdf((parsed["line"] - mu) / sigma)
    side = sides[parsed["team"]]
    if parsed["sport"] == "baseball":
        runline = model.get("runline")
        if runline is None:
            return None
        threshold, cover = runline  # the home side wins by more than `threshold` with probability `cover`
        if side == "home" and abs(threshold - parsed["line"]) < 1e-6:
            return cover
        if side == "away" and abs(-threshold - parsed["line"]) < 1e-6:
            return 1.0 - cover  # the away side by more than s is the home side by less than -s
        return None
    if model.get("margin") is None:
        return None
    mu, sigma = model["margin"]
    mu, line = (mu, model["line"]) if side == "home" else (-mu, -model["line"])
    if abs(parsed["line"] - mu) > num(p.get("max_strike_z"), PARAMS["max_strike_z"]) * sigma:
        return None
    low, high = min(line, parsed["line"]), max(line, parsed["line"])
    if any(low - EPS <= k <= high + EPS for key in KEY_MARGINS.get(parsed["league"], ()) for k in (key, -key)):
        return None  # a key number between the strike and the line: the smooth curve misprices it
    return 1.0 - NORMAL.cdf((parsed["line"] - mu) / sigma)


def fee(series, count, price, maker, rate):
    """The fee on one order of `count` contracts at `price`, as the book charges it: rounded up to
    $0.0001, the precision Kalshi charges at (ltcm/sim.py `kalshi_fee`). `rate` is the taker rate
    times the series multiplier this program assumes (`fee_multiplier`)."""
    if maker and series not in MAKER_FEE_SERIES:
        return 0.0
    charged = rate * (MAKER_SHARE if maker else 1.0) * count * price * (1.0 - price)
    return math.ceil(charged * 10000.0 - 1e-6) / 10000.0


def min_edge(p, parsed):
    """The edge a maker bid must clear: small on a winner, where Kalshi sits on the book's line, and
    larger on a spread or total ladder, where the model's own error is larger."""
    name = "min_edge_winner" if parsed["kind"] == "GAME" else "min_edge_ladder"
    return num(p.get(name), PARAMS[name])


def snap(price):
    return round(math.floor(price / TICK + EPS) * TICK, 2)


def ticker_key(ticker):
    """(series, event, game) of a ticker alone: its series, Kalshi's event (the first two segments)
    and the game it is about (the league and the event code, shared by a game's GAME, SPREAD and TOTAL)."""
    parts = str(ticker or "").upper().split("-")
    if len(parts) < 2:
        return None
    league, _ = league_of(parts[0])
    return parts[0], parts[0] + "-" + parts[1], (league or parts[0]) + ":" + parts[1]


def best_entry(market, parsed, fair, count_for, p, rate, floor, takers):
    """The entry this market offers now, as (edge a contract, leg, price, post_only), or None. On each
    leg: the ask, where the edge after the TAKER fee is at least take_edge (it fills now, so it is
    preferred); else a maker bid one tick over the best bid (never crossing), or at it, where that
    still clears the market's min_edge after the maker fee. Of the two legs, the larger edge."""
    bid, ask = num(market.get("yes_bid")), num(market.get("yes_ask"))
    if bid is None or ask is None or not 0.0 < bid < ask < 1.0:
        return None
    cap = num(p.get("max_price"), PARAMS["max_price"])
    found = []
    for leg, value, leg_bid, leg_ask in (("yes", fair, bid, ask), ("no", 1.0 - fair, round(1.0 - ask, 2), round(1.0 - bid, 2))):
        count = count_for(leg_ask)
        if takers and count and floor - EPS <= leg_ask <= cap + EPS:
            edge = value - leg_ask - fee(parsed["series"], count, leg_ask, False, rate) / count
            if edge >= num(p.get("take_edge"), PARAMS["take_edge"]) - EPS:
                found.append((edge, leg, leg_ask, False))
                continue
        price = snap(leg_bid + TICK) if leg_ask - leg_bid > TICK + EPS else leg_bid
        while price >= leg_bid - EPS:
            count = count_for(price)
            if floor - EPS <= price <= cap + EPS and count:
                edge = value - price - fee(parsed["series"], count, price, True, rate) / count
                if edge >= min_edge(p, parsed) - EPS:
                    found.append((edge, leg, price, True))
                    break
            price = round(price - TICK, 2)
    return max(found) if found else None


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    knob = lambda name: num(p.get(name), float(PARAMS[name]))
    now = when(ctx.get("now"))
    feeds = ctx.get("feeds") if isinstance(ctx.get("feeds"), dict) else {}
    rate = num((ctx.get("fees") or {}).get("kalshi_taker_rate"), TAKER_RATE) * knob("fee_multiplier")
    own = {str(s).upper() for s in NEEDS.get("series") or []}
    markets = [m for m in ctx.get("markets") or [] if isinstance(m, dict) and str(m.get("series") or "").upper() in own]
    shown = {str(m.get("market") or "").upper() for m in markets}
    positions = [x for x in ctx.get("positions") or [] if isinstance(x, dict) and num(x.get("quantity"), 0.0) > 0]
    orders = [o for o in ctx.get("open_orders") or [] if isinstance(o, dict)]
    bids = [o for o in orders if o.get("side") == "buy" and o.get("order_id") and (ticker_key(o.get("market")) or ("",))[0] in own]
    memory = ctx.get("memory") if isinstance(ctx.get("memory"), dict) else {}
    starts = {str(k): v for k, v in (memory.get("starts") or {}).items()} if isinstance(memory.get("starts"), dict) else {}
    priced_at = {str(k): num(v) for k, v in (memory.get("fair") or {}).items()} if isinstance(memory.get("fair"), dict) else {}
    buffer = 60.0 * knob("start_buffer_minutes")

    # A resting bid whose game is about to start goes first, whether or not its market is shown
    # (the House shows the soonest 200 markets, and a live game's can crowd it out).
    cancels = []
    for order in bids:
        began = when(starts.get((ticker_key(order.get("market")) or ("", "", ""))[1]))
        if now is not None and began is not None and (began - now).total_seconds() < buffer:
            cancels.append(str(order["order_id"]))
    if now is None or not feeds.get("odds") or not feeds.get("sports"):
        return {"intents": [], "cancels": cancels,
                "thought": "No sportsbook lines or scoreboard in this wake (the feeds are absent), so nothing was priced.",
                "memory": {k: v for k, v in (("starts", starts), ("fair", priced_at)) if v}}

    # Read every market, and learn which team code each title names.
    parsed_rows, learned = [], {}
    for market in markets:
        parsed = parse_market(market)
        if parsed is None:
            continue
        parsed_rows.append((market, parsed))
        if parsed["name"] and parsed["team"] not in (None, "TIE"):
            learned.setdefault(parsed["game"], {}).setdefault(parsed["team"], set()).add(words(parsed["name"]))
    boards, lines = {}, {}
    for league in {parsed["league"] for _, parsed in parsed_rows}:
        board = (feeds.get("sports") or {}).get(league)
        odds = (feeds.get("odds") or {}).get(league)
        boards[league] = prepare([e for e in (board or {}).get("events") or [] if isinstance(e, dict)])
        stamped = when((odds or {}).get("t"))
        lines[league] = {str(e.get("id")): (e, stamped) for e in (odds or {}).get("events") or [] if isinstance(e, dict)}

    # Price every market whose game is matched, has not started, and has fresh lines.
    games, priced, skipped = {}, {}, {}
    for market, parsed in parsed_rows:
        key = parsed["game"]
        if key not in games:
            games[key] = None
            why = None
            hit = match_game(parsed, boards.get(parsed["league"]) or {}, learned.get(key) or {})
            if hit is None:
                why = "unmatched"
            else:
                event, sides = hit
                start = when(event.get("start"))
                odds, stamped = lines[parsed["league"]].get(str(event.get("id")), (None, None))
                fetched = when((odds or {}).get("fetched")) or stamped
                if event.get("status") != "pre" or start is None or (start - now).total_seconds() < buffer:
                    why = "starting"
                elif odds is None or fetched is None or (now - fetched).total_seconds() > 60.0 * knob("stale_minutes"):
                    why = "stale lines"
                else:
                    model, why = game_model(consensus(odds, parsed["sport"]),
                                            {**event, "win_probability": odds.get("win_probability")}, parsed["sport"], p)
                    if model is not None:
                        games[key] = {"event": event, "sides": sides, "model": model, "start": start}
            if why:
                skipped[why] = skipped.get(why, 0) + 1
        game = games[key]
        if game is None or (parsed["team"] not in (None, "TIE") and parsed["team"] not in game["sides"]):
            continue
        fair = fair_yes(parsed, game["sides"], game["model"], p)
        if fair is not None and 0.0 < fair < 1.0:
            priced[parsed["ticker"]] = (market, parsed, fair)

    # What this agent already holds or is bidding, by event and by game.
    events, per_game, event_cost = set(), {}, {}
    for row in positions + [o for o in orders if o.get("side") == "buy"]:
        found = ticker_key(row.get("market"))
        if found is None:
            continue
        events.add(found[1])
        per_game.setdefault(found[2], set()).add(found[1])
        price = row.get("average_cost") if "average_cost" in row else row.get("limit_price")
        event_cost[found[1]] = event_cost.get(found[1], 0.0) + num(row.get("quantity"), 0.0) * num(price, 0.0)

    # A refused taker entry: the book holds this family to post-only until its taker record is positive.
    refused = [row for row in ctx.get("recent_order_outcomes") or []
               if isinstance(row, dict) and row.get("status") == "refused" and "post-only" in str(row.get("reason") or "")]
    real = int(num(ctx.get("rung"), 0.0) or 0) >= 2
    floor = max(knob("min_price"), LONGSHOT_FLOOR_REAL) if real else knob("min_price")

    cash = num(ctx.get("cash"), 0.0)
    reserved = sum(num(o.get("quantity"), 0.0) * num(o.get("limit_price"), 0.0) for o in orders if o.get("side") == "buy")
    free = [max(0.0, (cash - reserved) * 0.98)]  # 2% headroom for fees
    limits = ctx.get("limits") or {}
    equity = num(ctx.get("equity"), cash)
    remaining = (ctx.get("event_risk") or {}).get("remaining_by_market_usd") or {}

    def budget(ticker):
        event = ticker_key(ticker)[1]
        room = [knob("ticket_usd"), free[0], num(limits.get("max_order_usd"), knob("ticket_usd")),
                num(limits.get("max_position_usd"), knob("ticket_usd")), MAX_EVENT_SHARE * equity - event_cost.get(event, 0.0)]
        if num(remaining.get(ticker)) is not None:
            room.append(num(remaining.get(ticker)))
        return max(0.0, min(room))

    # Resting bids the fair, the lines or the clock no longer support.
    for order in bids:
        ticker = str(order.get("market") or "").upper()
        if str(order["order_id"]) in cancels or ticker not in shown:
            continue  # not shown this wake: nothing to judge it by but its start
        entry = priced.get(ticker)
        if entry is None:
            cancels.append(str(order["order_id"]))  # its game is unmatched, starting, stale or untrusted now
            continue
        leg, price = str(order.get("leg") or "yes"), num(order.get("limit_price"), 0.0)
        count = max(1, int(num(order.get("quantity"), 1.0)))
        edge = (entry[2] if leg == "yes" else 1.0 - entry[2]) - price - fee(entry[1]["series"], count, price, True, rate) / count
        sent = when(order.get("submitted_at"))
        then = priced_at.get(ticker)
        if then is not None and abs(entry[2] - then) >= knob("requote_move") - EPS:
            cancels.append(str(order["order_id"]))  # the line moved since the bid was priced
        elif edge < min_edge(p, entry[1]) / 2.0:
            cancels.append(str(order["order_id"]))
        elif sent is not None and (now - sent).total_seconds() > 60.0 * knob("requote_minutes"):
            better = best_entry(entry[0], entry[1], entry[2], lambda px, t=ticker: int(budget(t) / px + EPS), p, rate, floor, False)
            if better is not None and (better[1] != leg or abs(better[2] - price) > EPS):
                cancels.append(str(order["order_id"]))

    # New entries, best edge first: one market an event, max_per_game a game.
    offers = []
    for ticker, (market, parsed, fair) in priced.items():
        if parsed["event"] in events:
            continue
        takers = not refused and not any(ticker == str((row.get("instrument") or {}).get("market_id") or "").upper() for row in refused)
        entry = best_entry(market, parsed, fair, lambda px, t=ticker: int(budget(t) / px + EPS), p, rate, floor, takers)
        if entry is not None:
            offers.append((entry[0], ticker, entry, parsed, fair))
    offers.sort(key=lambda row: (-row[0], row[1]))
    intents = []
    for edge, ticker, (_, leg, price, post_only), parsed, fair in offers:
        if len(intents) >= min(int(knob("max_new")), MAX_INTENTS):
            break
        if parsed["event"] in events or len(per_game.get(parsed["game"], set())) >= int(knob("max_per_game")):
            continue
        quantity = int(budget(ticker) / price + EPS)
        if quantity < 1 or quantity * price < 1.0:
            continue
        free[0] -= quantity * price
        events.add(parsed["event"])
        per_game.setdefault(parsed["game"], set()).add(parsed["event"])
        event_cost[parsed["event"]] = event_cost.get(parsed["event"], 0.0) + quantity * price
        starts[parsed["event"]] = games[parsed["game"]]["event"].get("start")
        priced_at[ticker] = round(fair, 4)
        what = {"GAME": "ends in a tie" if parsed["team"] == "TIE" else f"{parsed['team']} wins",
                "SPREAD": f"{parsed['team']} by over {parsed['line']}", "TOTAL": f"over {parsed['line']}"}[parsed["kind"]]
        intent = {"market": ticker, "leg": leg, "side": "buy", "quantity": quantity, "type": "limit", "limit_price": price,
                  "reason": (f"The sportsbook line prices '{what}' at {fair:.3f} for YES; {leg.upper()} at {price:.2f} "
                             f"{'rests as a maker bid' if post_only else 'takes the ask'} and clears the fee by "
                             f"{edge * 100:.1f} cents a contract. Held to settlement.")}
        if post_only:
            intent["post_only"] = True
        intents.append(intent)

    # Keep the start of every event still bid on, and nothing else.
    live = {ticker_key(o.get("market"))[1] for o in bids if str(o["order_id"]) not in cancels} | {i["market"].rsplit("-", 1)[0] for i in intents}
    for event in live:
        found = games.get(ticker_key(event)[2])
        if found is not None and event not in starts:
            starts[event] = found["event"].get("start")
    resting = {str(o.get("market") or "").upper() for o in bids if str(o["order_id"]) not in cancels} | {i["market"] for i in intents}
    memory = {"starts": {event: starts[event] for event in sorted(live) if starts.get(event)},
              "fair": {ticker: priced_at[ticker] for ticker in sorted(resting) if priced_at.get(ticker) is not None}}

    leagues = "/".join(sorted({parsed["league"].upper() for _, parsed in parsed_rows})) or "No league"
    best = f"best edge {offers[0][0] * 100:.1f}c on {offers[0][1]}" if offers else "no edge cleared the fee and margin"
    missed = ", ".join(f"{count} {why}" for why, count in sorted(skipped.items())) or "none skipped"
    thought = (f"{leagues}: priced {len(priced)} of {len(markets)} markets on {sum(1 for g in games.values() if g)} "
               f"matched games ({missed}); {best}. Placed {len(intents)} bids and cancelled {len(cancels)}.")
    return {"intents": intents, "cancels": cancels, "thought": thought, "memory": {k: v for k, v in memory.items() if v}}
