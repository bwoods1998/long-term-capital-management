# sports-consensus: price Kalshi game markets (who wins, by how much, how many points) from the
# sportsbook line the House records (`odds`), and bid where Kalshi is off it by more than fees and a margin.
#
# EVIDENCE. UNMEASURED; practice is the test (lines recorded since Sept 24, 2026: no replay). The premise
# is thin: DraftKings' de-vigged win probability vs Kalshi's winner prints (Sept 24-25): MLB median gap
# 0.7c, p90 1.4c; WNBA 1.3c; NCAAF 1.8c. So winners are bid at a small edge and withdrawn when the line
# moves; ladders ask more; takers only at take_edge. ESPN carried one book (DraftKings).
#
# NEEDS. A game market's hours_to_close runs to its expected END (3 h after the start), so
# min_hours_to_close 3.0 shows a game up to its kickoff; max_markets 500 a college Saturday.
#
# MATCHING, NEVER GUESSED. A ticker names its game: KXNFLSPREAD-26OCT01PITCLE-PIT8 is the Oct 1 (New
# York date) game of PIT and CLE; baseball adds the first pitch and a doubleheader's number
# (26SEP251805CHCBOSG2). A market is priced only when exactly one game on the board has that date (and a
# first pitch within 15 minutes) and its two teams are exactly the two codes the ticker spells, either
# order. A code is a side when it is its ESPN abbreviation, a Kalshi alias, or a code a title of the
# game names with the side's name ("Northwestern wins" on -NW). Skipped: no game, two games, a code
# fitting both sides, a baseball ticker without its game number on a doubleheader day (a postponed
# game keeps its ticker and may settle on the other game), two game codes read as one board game.
#
# FAIR VALUE. Winner: the de-vigged moneyline (three-way with the draw in soccer), blended with ESPN's
# predictor by predictor_weight. Spread: home margin ~ Normal(mu, sigma_margin), mu from the home-signed
# line and its juice; skipped when its win chance and the moneyline's differ by more than ml_tolerance.
# Total: Normal(line moved by its juice, sigma_total). Only strikes within max_strike_z sigmas of the
# line. Football: no key number (3, 7, ...) between the strike and the line, a push included. Baseball
# spreads only at the book's own run line. Soccer: winner and tie only.
#
# ENTRIES. Only games `pre`, more than start_buffer_minutes out, with lines fetched within stale_minutes.
# YES or NO, one market an event (a ticker's first two segments), max_per_game a game: a post-only bid
# one tick over the bid (or at it) clearing min_edge after the maker fee; a limit at the ask only when
# the edge after the TAKER fee is at least take_edge, and post-only for MAKER_ONLY_HOURS after the real
# book refuses a taker. Nothing under 30 cents on real money. Fees as the book charges (ltcm/sim.py):
# taker 0.07 x C x P x (1 - P), rounded up to $0.0001; makers a quarter of it on MAKER_FEE_SERIES; the
# series multiplier (0.5 on KXMLB*) is not in ctx["fees"], so the full rate unless fee_multiplier lowers
# it, never under a series' own (FEE_MULTIPLIERS).
#
# EXITS. Held to settlement. A resting bid is cancelled inside start_buffer_minutes of its start (kept
# in memory), when the fair moved requote_move since it was priced, when its edge falls under half its
# min_edge, when its game cannot be priced fresh, or after requote_minutes when a better price is due.
# A bid whose market is not shown is priced from its ticker (a ladder suffix N is "over N - 0.5": all
# 5,129 of Sept 25-28) and its game's shown markets, else cancelled; all go when the feeds are absent.

from datetime import datetime, timedelta, timezone
from statistics import NormalDist
import json
import math
import re

NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "model-versus-market",
    "series": ["KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL"],
    "max_hours_to_close": 30,
    "min_hours_to_close": 3.0,
    "max_markets": 500,
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
            "min_price": [0.15, 0.5],
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
MAKER_SHARE = 0.25
# The series this can trade that charge makers (ltcm/data/kalshi_fees.json).
MAKER_FEE_SERIES = ("KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL", "KXNCAAFGAME", "KXNCAAFSPREAD", "KXNCAAFTOTAL",
                    "KXMLBGAME", "KXEPLGAME", "KXLALIGAGAME", "KXSERIEAGAME", "KXBUNDESLIGAGAME", "KXLIGUE1GAME",
                    "KXWNBAGAME", "KXNHLGAME", "KXNBAGAME", "KXNBASPREAD", "KXNBATOTAL")
MAX_EVENT_SHARE = 0.25  # allocator.max_event_share
LONGSHOT_FLOOR_REAL = 0.30  # allocator.longshot_floor_real
MAX_INTENTS = 8
MAX_CANCELS = 20  # the runner sends at most 20 cancels a decision
#: Resting bids at once: each keeps ~130 bytes of memory, and memory over 8 KB is dropped whole.
MAX_RESTING = 40
MAKER_ONLY_HOURS = 24
#: Kalshi's series fee multipliers under 1 (GET /series, Sept 25, 2026).
FEE_MULTIPLIERS = {"KXMLBGAME": 0.5, "KXMLBSPREAD": 0.5, "KXMLBTOTAL": 0.5}
# Kalshi series prefix -> the league key the House's feeds use, and the kind of game it is.
LEAGUES = (("KXNCAAF", "ncaaf", "football"), ("KXNFL", "nfl", "football"), ("KXMLB", "mlb", "baseball"),
           ("KXMLS", "mls", "soccer"), ("KXLIGAMX", "ligamx", "soccer"), ("KXEPL", "epl", "soccer"),
           ("KXLALIGA", "laliga", "soccer"), ("KXSERIEA", "seriea", "soccer"), ("KXBUNDESLIGA", "bundesliga", "soccer"),
           ("KXLIGUE1", "ligue1", "soccer"), ("KXEFLCHAMPIONSHIP", "championship", "soccer"))
# Kalshi codes that are not ESPN's abbreviation (the live boards of Sept 25, 2026): ESPN -> Kalshi.
ALIASES = {"nfl": {"JAX": ("JAC",), "WSH": ("WAS",)}, "mlb": {"ARI": ("AZ",), "CHW": ("CWS",)}, "ncaaf": {"ALB": ("ALBY",)},
           "mls": {"LA": ("LAG",), "RBNY": ("NYRB",), "DC": ("DCU",)}, "ligamx": {"SAN": ("SLA",), "UANL": ("TIG",)}}
#: A first pitch within this many minutes is the same game (Kalshi's CHC-BOS game 2 at 6:05 PM, ESPN's 6:00).
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


def mapping(value):
    """A dict, or {} for anything else."""
    return value if isinstance(value, dict) else {}


def rows(value):
    """The dicts of a list, or [] for anything else."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


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
    """A UTC moment as New York wall time (US DST rules), without a time-zone database."""
    utc = moment.astimezone(timezone.utc)
    march = datetime(utc.year, 3, 8, 7, tzinfo=timezone.utc)
    november = datetime(utc.year, 11, 1, 6, tzinfo=timezone.utc)
    begins = march + timedelta(days=(6 - march.weekday()) % 7)
    ends = november + timedelta(days=(6 - november.weekday()) % 7)
    return utc + timedelta(hours=-4 if begins <= utc < ends else -5)


def words(text):
    """A team name reduced for comparison: lower case, no accents or punctuation, `St.` as State/Saint."""
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
    """What the ticker and title say, or None if unreadable."""
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
           "clock": found.group(4), "teams": found.group(5), "number": found.group(6), "team": None, "name": None, "line": None}
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
    """The board by New York date: (game, first pitch in minutes, each side's abbreviation and names)."""
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
    """The Kalshi codes that are this side: its abbreviation, its aliases, and codes titled with its names."""
    abbrev, names = side
    return {abbrev, *(ALIASES.get(league) or {}).get(abbrev, ())} | {code for code, said in learned.items() if said & names}


def match_game(parsed, prepared, learned):
    """The one board game this market is about, as (event, {code: "home"|"away"}), or None (see MATCHING)."""
    readings = []
    teams = parsed["teams"]
    for event, minutes, sides in prepared.get(parsed["date"]) or []:
        codes = {name: codes_of(sides[name], parsed["league"], learned) for name in ("home", "away")}
        for first in codes["home"] | codes["away"]:
            second = teams[len(first):] if first and teams.startswith(first) else ""
            if not second:
                continue
            one = [name for name in ("home", "away") if first in codes[name]]
            other = [name for name in ("home", "away") if second in codes[name]]
            if len(one) == 1 and len(other) == 1 and one != other:
                readings.append((event, {first: one[0], second: other[0]}, minutes))
    if parsed["clock"]:
        if not parsed.get("number") and len({id(event) for event, _, _ in readings}) > 1:
            return None  # a doubleheader day, and the ticker does not say which game
        clock = int(parsed["clock"][:2]) * 60 + int(parsed["clock"][2:])
        readings = [reading for reading in readings if abs(reading[2] - clock) <= CLOCK_MINUTES]
    if len(readings) != 1:
        return None  # no game, or more than one reading: skipped, never guessed
    event, codes, _ = readings[0]
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
    lines = rows(game.get("lines"))
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
    if not sigma > 0 or not sigma_total > 0:
        return None, "no spread of outcomes"
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
    """One order's fee as the book charges it, rounded up to $0.0001 (`rate`: taker rate x multiplier)."""
    count, price = min(num(count, 0.0), 1e6), num(price, 0.0)
    if (maker and series not in MAKER_FEE_SERIES) or count <= 0 or not 0.0 < price < 1.0:
        return 0.0
    charged = rate * (MAKER_SHARE if maker else 1.0) * count * price * (1.0 - price)
    return math.ceil(charged * 10000.0 - 1e-6) / 10000.0


def min_edge(p, parsed):
    """The edge a maker bid must clear: small on a winner, larger on a ladder."""
    name = "min_edge_winner" if parsed["kind"] == "GAME" else "min_edge_ladder"
    return num(p.get(name), PARAMS[name])


def snap(price):
    return round(math.floor(price / TICK + EPS) * TICK, 2)


def fee_rate(series, rate, multiplier):
    """A series' taker rate: `rate` x `fee_multiplier`, never under the series' own multiplier."""
    return rate * max(min(multiplier, 1.0), FEE_MULTIPLIERS.get(series, 1.0))


def ladder_row(ticker):
    """A market row from its ticker alone (a ladder suffix N is "over N - 0.5")."""
    parts = str(ticker or "").upper().split("-")
    if len(parts) != 3:
        return None
    kind = kind_of(parts[0])
    strike = re.match(r"^([A-Z]*)(\d+)$", parts[2])
    if kind == "GAME":
        return {"market": ticker, "title": ""}
    if strike is None or (kind == "SPREAD") != bool(strike.group(1)):
        return None
    line = int(strike.group(2)) - 0.5
    title = f"{strike.group(1)} wins by over {line} points" if kind == "SPREAD" else f"Over {line} points"
    return {"market": ticker, "title": title, "strike": line}


def ticker_key(ticker):
    """(series, event, game) of a ticker: the event is its first two segments, the game league:code."""
    parts = str(ticker or "").upper().split("-")
    if len(parts) < 2:
        return None
    league, _ = league_of(parts[0])
    return parts[0], parts[0] + "-" + parts[1], (league or parts[0]) + ":" + parts[1]


def best_entry(market, parsed, fair, count_for, p, rate, floor, takers):
    """The entry this market offers now, (edge a contract, leg, price, post_only), or None: on each leg the
    ask where the edge after the taker fee is at least take_edge, else a maker bid a tick over the bid, or
    at it, clearing min_edge after the maker fee. Of the two legs, the larger edge."""
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
    ctx = mapping(ctx)
    p = {**PARAMS, **mapping(ctx.get("params"))}
    knob = lambda name: num(p.get(name), float(PARAMS[name]))
    now = when(ctx.get("now"))
    feeds = mapping(ctx.get("feeds"))
    odds_feed, sports_feed = mapping(feeds.get("odds")), mapping(feeds.get("sports"))
    base_rate = num(mapping(ctx.get("fees")).get("kalshi_taker_rate"))
    base_rate = base_rate if base_rate is not None and 0.0 < base_rate <= 1.0 else TAKER_RATE
    rate_of = lambda series: fee_rate(series, base_rate, knob("fee_multiplier"))
    own = {str(s).upper() for s in NEEDS.get("series") or []}
    markets = [m for m in rows(ctx.get("markets")) if str(m.get("series") or "").upper() in own]
    shown = {str(m.get("market") or "").upper() for m in markets}
    positions = [x for x in rows(ctx.get("positions")) if num(x.get("quantity"), 0.0) > 0]
    buys = [o for o in rows(ctx.get("open_orders")) if o.get("side") == "buy"]
    bids = [o for o in buys if o.get("order_id") and (ticker_key(o.get("market")) or ("",))[0] in own]
    memory = mapping(ctx.get("memory"))
    starts = {str(k): v for k, v in mapping(memory.get("starts")).items() if isinstance(v, str)}
    priced_at = {str(k): num(v) for k, v in mapping(memory.get("fair")).items()}
    buffer = 60.0 * knob("start_buffer_minutes")

    # A refused taker entry holds the family to post-only; remembered, as it leaves the outcomes.
    maker_only = when(memory.get("maker_only_until"))
    for row in rows(ctx.get("recent_order_outcomes")):
        if row.get("status") == "refused" and "post-only" in str(row.get("reason") or "") and now is not None:
            until = (when(row.get("at")) or now) + timedelta(hours=MAKER_ONLY_HOURS)
            maker_only = until if maker_only is None or until > maker_only else maker_only
    takers = now is not None and (maker_only is None or maker_only <= now)

    # A resting bid whose game is about to start goes first, whether or not its market is shown.
    urgent, later = [], []
    for order in bids:
        began = when(starts.get((ticker_key(order.get("market")) or ("", "", ""))[1]))
        if now is not None and began is not None and (began - now).total_seconds() < buffer:
            urgent.append(str(order["order_id"]))

    def finish(intents, games, thought):
        """The decision: cancels start-first (the runner sends 20), and the memory of every bid still resting."""
        cancels = list(dict.fromkeys(urgent + later))[:MAX_CANCELS]
        kept = [o for o in bids if str(o["order_id"]) not in cancels]
        live = {ticker_key(o.get("market"))[1] for o in kept} | {i["market"].rsplit("-", 1)[0] for i in intents}
        for event in live:
            found = games.get(ticker_key(event)[2])
            if found is not None and event not in starts:
                starts[event] = found["event"].get("start")
        resting = {str(o.get("market") or "").upper() for o in kept} | {i["market"] for i in intents}
        out = {"starts": {event: starts[event] for event in sorted(live) if isinstance(starts.get(event), str)},
               "fair": {ticker: priced_at[ticker] for ticker in sorted(resting) if priced_at.get(ticker) is not None}}
        if maker_only is not None and now is not None and maker_only > now:
            out["maker_only_until"] = maker_only.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out = {k: v for k, v in out.items() if v}
        if len(json.dumps(out)) > 7800:
            out.pop("fair", None)  # never the starts: they cancel a bid at its game's start
        return {"intents": intents, "cancels": cancels, "thought": thought.replace("{cancelled}", str(len(cancels))), "memory": out}

    if now is None or not odds_feed or not sports_feed:
        later.extend(str(o["order_id"]) for o in bids)  # no line to stand behind a resting bid
        return finish([], {}, "No sportsbook lines or scoreboard in this wake (the feeds are absent), so nothing was priced; "
                              "cancelled {cancelled} resting bids.")

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
        odds = mapping(odds_feed.get(league))
        boards[league] = prepare(rows(mapping(sports_feed.get(league)).get("events")))
        stamped = when(odds.get("t"))
        lines[league] = {str(e.get("id")): (e, stamped) for e in rows(odds.get("events"))}

    # Match every game once. One scoreboard game is one Kalshi game: two game codes read as one are neither.
    firsts, hits, claimed = {}, {}, {}
    for _, parsed in parsed_rows:
        firsts.setdefault(parsed["game"], parsed)
    for key, parsed in firsts.items():
        hits[key] = match_game({**parsed, "team": None}, boards.get(parsed["league"]) or {}, learned.get(key) or {})
        if hits[key] is not None:
            claimed.setdefault((parsed["league"], str(hits[key][0].get("id"))), []).append(key)
    doubled = {key for keys in claimed.values() if len(keys) > 1 for key in keys}

    # Price every market whose game is matched, has not started, and has fresh lines.
    games, priced, skipped, starting = {}, {}, {}, set()
    for key, parsed in firsts.items():
        games[key], why = None, None
        if hits[key] is None or key in doubled:
            why = "unmatched" if hits[key] is None else "ambiguous"
        else:
            event, sides = hits[key]
            start = when(event.get("start"))
            odds, stamped = lines[parsed["league"]].get(str(event.get("id")), (None, None))
            odds = odds or {}
            fetched = when(odds.get("fetched")) if "fetched" in odds else stamped
            if fetched is not None and stamped is not None and stamped < fetched:
                fetched = stamped
            if event.get("status") != "pre" or start is None or (start - now).total_seconds() < buffer:
                why = "starting"
                starting.add(key)
            elif not odds or fetched is None or (now - fetched).total_seconds() > 60.0 * knob("stale_minutes"):
                why = "stale lines"
            else:
                model, why = game_model(consensus(odds, parsed["sport"]),
                                        {**event, "win_probability": odds.get("win_probability")}, parsed["sport"], p)
                if model is not None:
                    games[key] = {"event": event, "sides": sides, "model": model, "start": start}
        if why:
            skipped[why] = skipped.get(why, 0) + 1
    for market, parsed in parsed_rows:
        game = games[parsed["game"]]
        if game is None or (parsed["team"] not in (None, "TIE") and parsed["team"] not in game["sides"]):
            continue
        fair = fair_yes(parsed, game["sides"], game["model"], p)
        if fair is not None and 0.0 < fair < 1.0:
            priced[parsed["ticker"]] = (market, parsed, fair)

    # What this agent holds or bids, by event and game (a cost it cannot read counts as a dollar).
    events, per_game, event_cost = set(), {}, {}
    for row in positions + buys:
        found = ticker_key(row.get("market"))
        if found is None:
            continue
        events.add(found[1])
        per_game.setdefault(found[2], set()).add(found[1])
        price = num(row.get("average_cost") if "average_cost" in row else row.get("limit_price"))
        price = price if price is not None and 0.0 < price <= 1.0 else 1.0
        event_cost[found[1]] = event_cost.get(found[1], 0.0) + max(0.0, num(row.get("quantity"), 0.0)) * price

    rung = num(ctx.get("rung"))
    real = rung is None or rung >= 2  # a snapshot that does not say is held to the real floor
    floor = max(knob("min_price"), LONGSHOT_FLOOR_REAL) if real else knob("min_price")

    cash = num(ctx.get("cash"), 0.0)
    reserved = sum(max(0.0, num(o.get("quantity"), 0.0)) * max(0.0, num(o.get("limit_price"), 0.0)) for o in buys)
    free = [max(0.0, (cash - reserved) * 0.98)]  # 2% headroom
    limits = mapping(ctx.get("limits"))
    equity = num(ctx.get("equity"), cash)
    remaining = mapping(mapping(ctx.get("event_risk")).get("remaining_by_market_usd"))

    def budget(ticker):
        """The dollars one entry may put up, cash aside: the ticket, the limits, the event's quarter of equity, its risk room."""
        event = ticker_key(ticker)[1]
        room = [knob("ticket_usd"), num(limits.get("max_order_usd"), knob("ticket_usd")),
                num(limits.get("max_position_usd"), knob("ticket_usd")), MAX_EVENT_SHARE * equity - event_cost.get(event, 0.0)]
        if num(remaining.get(ticker)) is not None:
            room.append(num(remaining.get(ticker)))
        return max(0.0, min(room))

    def counter(ticker, series):
        """Whole contracts at a price: within the budget, and within free cash with the taker's fee on top."""
        rate = rate_of(series)
        return lambda price: int(max(0.0, min(budget(ticker) / price, free[0] / (price * (1.0 + rate * (1.0 - price))))) + EPS) if price > 0 else 0

    # Resting bids the fair, the lines or the clock no longer support, each judged by its own ticker.
    for order in bids:
        oid = str(order["order_id"])
        ticker = str(order.get("market") or "").upper()
        series, _, key = ticker_key(ticker)
        if key in starting:
            urgent.append(oid)
            continue
        leg, price, count = order.get("leg"), num(order.get("limit_price")), num(order.get("quantity"))
        if leg not in ("yes", "no") or price is None or not 0.0 < price < 1.0 or count is None or count <= 0:
            later.append(oid)  # an order it cannot read is not one it can stand behind
            continue
        entry = priced.get(ticker)
        if ticker not in shown:
            game, row = games.get(key), ladder_row(ticker)
            parsed = parse_market(row) if game is not None and row is not None else None
            fair = None
            if parsed is not None and (parsed["team"] in (None, "TIE") or parsed["team"] in game["sides"]):
                fair = fair_yes(parsed, game["sides"], game["model"], p)
            entry = (None, parsed, fair) if fair is not None and 0.0 < fair < 1.0 and priced_at.get(ticker) is not None else None
        if entry is None:
            later.append(oid)  # its game is not shown, unmatched, starting, stale or untrusted now
            continue
        count = max(1, int(min(count, 1e6)))
        edge = (entry[2] if leg == "yes" else 1.0 - entry[2]) - price - fee(series, count, price, True, rate_of(series)) / count
        sent = when(order.get("submitted_at"))
        then = priced_at.get(ticker)
        if then is not None and abs(entry[2] - then) >= knob("requote_move") - EPS:
            later.append(oid)  # the line moved since the bid was priced
        elif edge < min_edge(p, entry[1]) / 2.0:
            later.append(oid)
        elif entry[0] is not None and sent is not None and (now - sent).total_seconds() > 60.0 * knob("requote_minutes"):
            better = best_entry(entry[0], entry[1], entry[2], counter(ticker, series), p, rate_of(series), floor, False)
            if better is not None and (better[1] != leg or abs(better[2] - price) > EPS):
                later.append(oid)
    cancelled = set(list(dict.fromkeys(urgent + later))[:MAX_CANCELS])
    resting = sum(1 for o in bids if str(o["order_id"]) not in cancelled)

    # New entries, best edge first: one market an event, max_per_game a game, MAX_RESTING bids at once.
    offers = []
    for ticker, (market, parsed, fair) in priced.items():
        if parsed["event"] in events:
            continue
        entry = best_entry(market, parsed, fair, counter(ticker, parsed["series"]), p, rate_of(parsed["series"]), floor, takers)
        if entry is not None:
            offers.append((entry[0], ticker, entry, parsed, fair))
    offers.sort(key=lambda row: (-row[0], row[1]))
    intents = []
    for edge, ticker, (_, leg, price, post_only), parsed, fair in offers:
        if len(intents) >= min(int(knob("max_new")), MAX_INTENTS, MAX_RESTING - resting):
            break
        if parsed["event"] in events or len(per_game.get(parsed["game"], set())) >= int(knob("max_per_game")):
            continue
        quantity = counter(ticker, parsed["series"])(price)
        if quantity < 1 or quantity * price < 1.0:
            continue
        free[0] -= quantity * price * (1.0 + rate_of(parsed["series"]) * (1.0 - price))
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

    leagues = "/".join(sorted({parsed["league"].upper() for _, parsed in parsed_rows})) or "No league"
    best = f"best edge {offers[0][0] * 100:.1f}c on {offers[0][1]}" if offers else "no edge cleared the fee and margin"
    missed = ", ".join(f"{count} {why}" for why, count in sorted(skipped.items())) or "none skipped"
    thought = (f"{leagues}: priced {len(priced)} of {len(markets)} markets on {sum(1 for g in games.values() if g)} "
               f"matched games ({missed}); {best}. Placed {len(intents)} bids and cancelled {{cancelled}}.")
    return finish(intents, games, thought)
