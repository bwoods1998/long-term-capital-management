# sports-h2h: price Kalshi's head-to-head winner markets of an individual sport (a UFC fight) from
# the sportsbook moneyline the House records, and bid where Kalshi is off it by more than fees and a
# margin. The sibling of sports_consensus.py for sports whose sides are PEOPLE, not teams: a fight
# is found by its fighters' names, never by a team code.
#
# THE IDEA. A sportsbook's closing moneyline is the best public forecast of a fight there is, and
# its margin can be taken out of its two prices. Kalshi lists every fight of a card as two binary
# contracts ("Vanessa Demopoulos wins"), often thinly; where one trades below the book's de-vigged
# probability by more than the fee and a margin, a resting maker bid there is a bet the book is right.
#
# THE EVIDENCE. UNMEASURED as a strategy: there is no replay (the House records the lines from the
# day this was written), so practice is the test. The premise was measured once, live, at 10:50Z on
# Sept 25, 2026, on the Sept 26 Fight Night: ESPN's core API carried DraftKings' moneyline for 10 of
# the card's 12 bouts; 11 of Kalshi's 12 fights matched a bout by name (the twelfth was a card
# change: Kalshi's "Amaya vs Machado" is ESPN's "Tina Black vs Melissa Amaya"), 9 of them with a line,
# and Kalshi's mid sat within 1.1 cents of the de-vigged line on 16 of their 18 markets (median
# 0.55c); the one fight off it was Dumont Viana vs Perez, Perez 2.15 cents rich. So on fights, as on MLB,
# Kalshi mostly sits on the book: the edge asked is small, a bid is withdrawn when the line moves,
# and most wakes place nothing. Tennis, golf, cricket and F1 were probed the same morning: ESPN
# carries no line for them, so this program has nothing to price them by.
#
# WHAT IT NEEDS. The fight series (KXUFCFIGHT), the `odds` feed (each bout's lines, with when they
# were fetched and the ESPN ids of the two athletes the prices are for) and the `sports` board (a
# row a bout: each bout's start, status and its two athletes' names and ids). Woken every ten
# minutes. Kalshi expects a fight's result hours after the card starts (the main event's at 06:40Z
# for a 00:00Z main card), so min_hours_to_close is small and the start is judged from ESPN.
#
# HOW A MARKET IS MATCHED TO A FIGHT, WITHOUT GUESSING. KXUFCFIGHT-26SEP26DEMJAU-DEM "Vanessa
# Demopoulos wins" is the Sept 26 fight of DEM and JAU, and this market is DEM's. It is read only
# when its code begins a word of its title's name. A name is compared after accents, dots,
# apostrophes and suffixes (Jr, Sr, II, III) are taken out and hyphens split it: two names are one
# person when their words are the same (in any order: "Wang Cong" is "Cong Wang"), when they are the
# same letters run together ("Alateng Heili" is ESPN's "Alatengheili"), or when the given names agree
# (an initial agrees with a name it begins) and every other word of the shorter name is in the
# longer, in order (a compound surname one side shortens: "Norma Dumont Viana" is ESPN's "Norma
# Dumont"). A Kalshi fight is priced only when exactly one bout on the board, within a day of the
# ticker's date, has each of the event's shown names matching exactly one of its two athletes, and
# different ones; when only one of the two markets is shown, the ticker's other code must begin a
# word of the other athlete's name. A card change ("Amaya vs Machado" on Kalshi, "Tina Black vs
# Melissa Amaya" on ESPN) matches nothing and is skipped. The prices are joined to the athletes by
# their ESPN ids, never by home and away.
#
# FAIR VALUE. The mean over providers of each athlete's de-vigged two-way probability. A sportsbook
# refunds a moneyline on a draw; Kalshi resolves a draw or a no contest 50/50 for both fighters
# (the market's rules), so a YES is worth p + void_share x (0.5 - p): void_share, about 1.5% of UFC
# fights ending in a draw or no contest, is an estimate, not a measurement.
#
# WHEN IT TRADES. Only fights that have not started, whose bout starts more than
# start_buffer_minutes from now (a bout's start is its card segment's, so a late fight is left
# early, never entered late), and whose lines were fetched within stale_minutes. It buys YES or NO,
# never both and at most one market a fight: a post-only maker bid one tick over the best bid where
# that clears min_edge after the maker fee, else at the bid; it takes the ask only when the edge
# after the TAKER fee is at least take_edge, and never on a book that has refused its taker entry.
# Fees as the book charges them: taker 0.07 x C x P x (1 - P) per order, rounded up to $0.0001;
# makers pay a quarter of that only on the series that charge makers (KXUFCFIGHT does not: its fee
# type is `quadratic`, GET /series, Sept 25, 2026; the tennis series do). An order is as many
# contracts as its cost AND its fee fit in the free cash.
#
# HOW IT EXITS. It does not sell: a contract is held to settlement. A resting bid is cancelled when
# its fight is within start_buffer_minutes of the start, when the fair has moved requote_move since
# the bid was priced, when its edge falls under half of min_edge, when the fight can no longer be
# priced, or after requote_minutes when a better price is due.

from datetime import datetime, timedelta, timezone
import math
import re

NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "model-versus-market",
    "series": ["KXUFCFIGHT"],
    "max_hours_to_close": 42,
    "min_hours_to_close": 0.5,
    "max_markets": 200,
    "wake_minutes": 10,
    "feeds": {"odds": ["ufc"], "sports": ["ufc"]},
    "parameter_rules": {
        "bounds": {
            "min_edge": [0.005, 0.1],
            "take_edge": [0.04, 0.25],
            "requote_move": [0.005, 0.05],
            "ticket_usd": [1.0, 50.0],
            "max_new": [1, 6],
            "start_buffer_minutes": [10, 120],
            "stale_minutes": [30, 240],
            "requote_minutes": [10, 240],
            "void_share": [0.0, 0.05],
            "min_price": [0.15, 0.5],
            "max_price": [0.5, 0.97],
            "fee_multiplier": [0.5, 1.0],
        },
        "ordered": [["min_edge", "take_edge"], ["min_price", "max_price"]],
    },
}
PARAMS = {
    "min_edge": 0.02,
    "take_edge": 0.06,
    "requote_move": 0.01,
    "ticket_usd": 10.0,
    "max_new": 3,
    "start_buffer_minutes": 20,
    "stale_minutes": 90,
    "requote_minutes": 60,
    "void_share": 0.015,
    "min_price": 0.15,
    "max_price": 0.9,
    "fee_multiplier": 1.0,
}

TICK = 0.01
EPS = 1e-9
TAKER_RATE = 0.07
MAKER_SHARE = 0.25
# The head-to-head series that charge makers (the sports desk's `maker_fee_series`).
MAKER_FEE_SERIES = ("KXATPMATCH", "KXWTAMATCH")
MAX_EVENT_SHARE = 0.25  # allocator.max_event_share
LONGSHOT_FLOOR_REAL = 0.30  # allocator.longshot_floor_real: no real entry under 30 cents
LONGSHOT_FLOOR = 0.15  # the book's min_event_price, which practice books keep: no entry under 15 cents
MAX_INTENTS = 8
# Kalshi series -> the league key the House's feeds use (a sport ESPN prices; Sept 25, 2026).
SPORTS = {"KXUFCFIGHT": "ufc"}
DATE_SLACK_DAYS = 1
MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10,
          "NOV": 11, "DEC": 12}
EVENT_CODE = re.compile(r"^(\d{2})([A-Z]{3})(\d{2})([A-Z]+)$")
WINS = re.compile(r"^(.+?) wins\??$")
SUFFIXES = ("jr", "sr", "ii", "iii", "iv")
FOLD = str.maketrans({**{c: "a" for c in "áàâäãåāăą"}, **{c: "c" for c in "çćč"}, **{c: "d" for c in "ďđð"},
                      **{c: "e" for c in "éèêëēėęě"}, **{c: "g" for c in "ğ"}, **{c: "i" for c in "íìîïīįı"},
                      **{c: "l" for c in "łľĺ"}, **{c: "n" for c in "ñńň"}, **{c: "o" for c in "óòôöõøōő"},
                      **{c: "r" for c in "řŕ"}, **{c: "s" for c in "śšşș"}, **{c: "t" for c in "ťţț"},
                      **{c: "u" for c in "úùûüūůűų"}, **{c: "y" for c in "ýÿ"}, **{c: "z" for c in "źžż"},
                      "ə": "e", "ß": "ss", "æ": "ae", "œ": "oe", "þ": "th"})
# Taken out of a name before it is split: dots, apostrophes (and the letters written as one) and the
# combining accents a decomposed or dotted capital leaves ("İ".lower() is "i" + U+0307).
DROP = re.compile("[.'`\u2019\u02bb\u02bc\u0300-\u036f]")


def table(value):
    return value if isinstance(value, dict) else {}


def listed(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def num(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def when(text):
    try:
        clean = str(text).strip()
        if clean[-1:] in "Zz":
            clean = clean[:-1] + "+00:00"
        moment = datetime.fromisoformat(clean)
    except (TypeError, ValueError, IndexError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def new_york(moment):
    """A UTC moment as New York wall time (US daylight time), without a time-zone database."""
    utc = moment.astimezone(timezone.utc)
    march = datetime(utc.year, 3, 8, 7, tzinfo=timezone.utc)
    november = datetime(utc.year, 11, 1, 6, tzinfo=timezone.utc)
    begins = march + timedelta(days=(6 - march.weekday()) % 7)
    ends = november + timedelta(days=(6 - november.weekday()) % 7)
    return utc + timedelta(hours=-4 if begins <= utc < ends else -5)


def person(text):
    """A person's name as the words compared: lower case, accents folded, dots, apostrophes and
    combining accents out, split on anything but a letter or digit (hyphens included), Jr/Sr/II/III/IV
    dropped. A letter the fold does not know stays inside its word: split there, a name would leave a
    one-letter piece that `given` reads as an initial ("Jəfər Smith" would be any "J... Smith")."""
    clean = DROP.sub("", str(text or "").lower().translate(FOLD))
    return tuple(word for word in re.findall(r"[^\W_]+", clean) if word not in SUFFIXES)


def given(a, b):
    return a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b))


def same_person(a, b):
    """Are these two names (as `person` words) one person? See the header: never a surname alone."""
    if not a or not b:
        return False
    if a == b or "".join(a) == "".join(b) or (len(a) == len(b) and sorted(a) == sorted(b)):
        return True
    short, long = (a, b) if len(a) < len(b) else (b, a)
    if len(short) < 2 or not given(short[0], long[0]):
        return False
    rest = iter(long[1:])  # an iterator: each word must be found AFTER the one before it
    return all(any(word == other for other in rest) for word in short[1:])


def parse_h2h(row):
    """What a head-to-head market's ticker and title say, or None when they cannot both be read or
    disagree (its code must begin a word of its title's name)."""
    ticker = str(row.get("market") or "").upper()
    parts = ticker.split("-")
    if len(parts) != 3 or parts[0] not in SPORTS:
        return None
    found, said = EVENT_CODE.match(parts[1]), WINS.match(str(row.get("title") or "").strip())
    if found is None or said is None or found.group(2) not in MONTHS:
        return None
    code, letters, name = parts[2], found.group(4), person(said.group(1))
    if not name or len(code) >= len(letters) or not (letters.startswith(code) or letters.endswith(code)):
        return None
    if not any(word.startswith(code.lower()) for word in name):
        return None
    try:  # a date that is no day (26SEP31) is no fight
        datetime(2000 + int(found.group(1)), MONTHS[found.group(2)], int(found.group(3)))
    except ValueError:
        return None
    return {"ticker": ticker, "series": parts[0], "league": SPORTS[parts[0]], "event": parts[0] + "-" + parts[1],
            "game": parts[0] + ":" + parts[1], "date": (2000 + int(found.group(1)), MONTHS[found.group(2)], int(found.group(3))),
            "letters": letters, "code": code, "name": name, "team": said.group(1), "kind": "GAME"}


def bouts_of(board):
    """The board's bouts with their New York date and each side's name words and ESPN id."""
    out = []
    for bout in board:
        start = when(bout.get("start"))
        home, away = bout.get("home"), bout.get("away")
        if start is None or not isinstance(home, dict) or not isinstance(away, dict) or not home.get("id") or not away.get("id"):
            continue
        if str(home["id"]) == str(away["id"]):
            continue  # one athlete on both sides is no bout
        try:
            local = new_york(start)
        except OverflowError:
            continue
        out.append((bout, datetime(local.year, local.month, local.day),
                    {side: (person(team.get("team")), str(team["id"])) for side, team in (("home", home), ("away", away))}))
    return out


def match_bout(shown, bouts):
    """The one bout a Kalshi fight is, as (bout, {code: athlete id}), or None. `shown` is the event's
    parsed markets (one or two). Each name must be exactly one of the bout's athletes, and different
    ones; a lone market's other code must begin a word of the other athlete's name."""
    first = shown[0]
    day = datetime(*first["date"])
    found = []
    for bout, local, sides in bouts:
        if abs((local - day).days) > DATE_SLACK_DAYS:
            continue
        ids, fits = {}, True
        for parsed in shown:
            hits = [side for side in ("home", "away") if same_person(parsed["name"], sides[side][0])]
            if len(hits) != 1:
                fits = False
                break
            ids[parsed["code"]] = hits[0]
        if not fits or len(set(ids.values())) != len(ids):
            continue
        if len(ids) == 1:
            other = first["letters"][len(first["code"]):] if first["letters"].startswith(first["code"]) else first["letters"][:-len(first["code"])]
            rival = sides["away" if ids[first["code"]] == "home" else "home"][0]
            if not other or not any(word.startswith(other.lower()) for word in rival):
                continue
        found.append((bout, {code: sides[side][1] for code, side in ids.items()}))
    return found[0] if len(found) == 1 else None


def bout_fair(odds, bout, void):
    """{athlete id: fair YES}: the mean over providers of each athlete's de-vigged probability, joined
    by the athletes' ESPN ids (never home and away), moved toward 0.5 by the draw/no-contest share."""
    ids = (str(bout["home"]["id"]), str(bout["away"]["id"]))
    if ids[0] == ids[1]:
        return None
    seen = {ids[0]: [], ids[1]: []}
    for line in listed(table(odds).get("lines")):
        pair = (str(line.get("home_athlete") or ""), str(line.get("away_athlete") or ""))
        home, away = num(line.get("implied_home")), num(line.get("implied_away"))
        if set(pair) != set(ids) or home is None or away is None or line.get("draw_ml") is not None:
            continue
        seen[pair[0]].append(home)
        seen[pair[1]].append(away)
    if not seen[ids[0]] or not seen[ids[1]]:
        return None
    fair = {}
    for athlete, values in seen.items():
        p = sum(values) / len(values)
        fair[athlete] = p + void * (0.5 - p)
    return fair


def fee(series, count, price, maker, rate):
    if maker and series not in MAKER_FEE_SERIES:
        return 0.0
    charged = rate * (MAKER_SHARE if maker else 1.0) * count * price * (1.0 - price)
    return math.ceil(charged * 10000.0 - 1e-6) / 10000.0


def snap(price):
    return round(math.floor(price / TICK + EPS) * TICK, 2)


def series_of(ticker):
    return str(ticker or "").upper().split("-")[0]


def event_of(ticker):
    parts = str(ticker or "").upper().split("-")
    return parts[0] + "-" + parts[1] if len(parts) >= 2 else None


def best_entry(market, parsed, fair, count_for, p, rate, floor, takers):
    """(edge a contract, leg, price, post_only) this market offers now, or None: the ask where the
    edge after the taker fee is at least take_edge, else a maker bid one tick over the best bid (or
    at it) that clears min_edge after the maker fee. Of the two legs, the larger edge."""
    bid, ask = num(market.get("yes_bid")), num(market.get("yes_ask"))
    if bid is None or ask is None or not 0.0 < bid < ask < 1.0:
        return None
    cap, found = num(p.get("max_price"), PARAMS["max_price"]), []
    for leg, value, leg_bid, leg_ask in (("yes", fair, bid, ask), ("no", 1.0 - fair, round(1.0 - ask, 2), round(1.0 - bid, 2))):
        count = count_for(leg_ask, False)
        if takers and count and floor - EPS <= leg_ask <= cap + EPS:
            edge = value - leg_ask - fee(parsed["series"], count, leg_ask, False, rate) / count
            if edge >= num(p.get("take_edge"), PARAMS["take_edge"]) - EPS:
                found.append((edge, leg, leg_ask, False))
                continue
        price = snap(leg_bid + TICK) if leg_ask - leg_bid > TICK + EPS else leg_bid
        while price >= leg_bid - EPS:
            count = count_for(price, True)
            if floor - EPS <= price <= cap + EPS and count:
                edge = value - price - fee(parsed["series"], count, price, True, rate) / count
                if edge >= num(p.get("min_edge"), PARAMS["min_edge"]) - EPS:
                    found.append((edge, leg, price, True))
                    break
            price = round(price - TICK, 2)
    return max(found) if found else None


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    knob = lambda name: num(p.get(name), float(PARAMS[name]))
    now = when(ctx.get("now"))
    feeds = ctx.get("feeds") if isinstance(ctx.get("feeds"), dict) else {}
    rate = num(table(ctx.get("fees")).get("kalshi_taker_rate"), TAKER_RATE) * knob("fee_multiplier")
    own = {str(s).upper() for s in NEEDS.get("series") or []}
    markets = [m for m in listed(ctx.get("markets")) if str(m.get("series") or "").upper() in own]
    shown = {str(m.get("market") or "").upper() for m in markets}
    positions = [x for x in listed(ctx.get("positions")) if num(x.get("quantity"), 0.0) > 0]
    orders = listed(ctx.get("open_orders"))
    bids = [o for o in orders if o.get("side") == "buy" and o.get("order_id") and str(o.get("market") or "").upper().split("-")[0] in own]
    memory = ctx.get("memory") if isinstance(ctx.get("memory"), dict) else {}
    starts = {str(k): v for k, v in (memory.get("starts") or {}).items()} if isinstance(memory.get("starts"), dict) else {}
    priced_at = {str(k): num(v) for k, v in (memory.get("fair") or {}).items()} if isinstance(memory.get("fair"), dict) else {}
    buffer = 60.0 * knob("start_buffer_minutes")

    # A resting bid whose fight is about to start goes first, whether or not its market is shown.
    cancels = []
    for order in bids:
        began = when(starts.get(event_of(order.get("market"))))
        if now is not None and began is not None and (began - now).total_seconds() < buffer:
            cancels.append(str(order["order_id"]))
    if now is None or not feeds.get("odds") or not feeds.get("sports"):
        return {"intents": [], "cancels": cancels,
                "thought": "No sportsbook lines or scoreboard in this wake (the feeds are absent), so nothing was priced.",
                "memory": {k: v for k, v in (("starts", starts), ("fair", priced_at)) if v}}

    # Read every market, grouped by fight (Kalshi's event).
    events = {}
    for market in markets:
        parsed = parse_h2h(market)
        if parsed is not None:
            events.setdefault(parsed["event"], []).append((market, parsed))
    boards, lines = {}, {}
    for league in {rows[0][1]["league"] for rows in events.values()}:
        board, odds = table(table(feeds.get("sports")).get(league)), table(table(feeds.get("odds")).get(league))
        boards[league] = bouts_of(listed(board.get("events")))
        stamped = when(odds.get("t"))
        lines[league] = {str(e.get("id")): (e, stamped) for e in listed(odds.get("events"))}

    # Price every fight matched to exactly one bout that has not started and has fresh lines.
    fights, priced, skipped = {}, {}, {}
    for event, rows in sorted(events.items()):
        by_code = {}
        for market, parsed in rows:
            by_code.setdefault(parsed["code"], (market, parsed))
        league, why = rows[0][1]["league"], None
        hit = match_bout([parsed for _, parsed in by_code.values()], boards.get(league) or []) if len(by_code) <= 2 else None
        if hit is None:
            why = "unmatched"
        else:
            bout, athletes = hit
            start = when(bout.get("start"))
            odds, stamped = lines[league].get(str(bout.get("id")), (None, None))
            fetched = when((odds or {}).get("fetched")) or stamped
            fair = bout_fair(odds, bout, knob("void_share")) if odds is not None else None
            if bout.get("status") != "pre" or start is None or (start - now).total_seconds() < buffer:
                why = "starting"
            elif odds is None or fetched is None or (now - fetched).total_seconds() > 60.0 * knob("stale_minutes"):
                why = "stale lines"
            elif fair is None:
                why = "no line"
            else:
                fights[event] = {"bout": bout, "start": bout.get("start")}
                for code, (market, parsed) in by_code.items():
                    value = fair[athletes[code]]
                    if 0.0 < value < 1.0:
                        priced[parsed["ticker"]] = (market, parsed, value)
        if why:
            skipped[why] = skipped.get(why, 0) + 1

    # What this agent already holds or is bidding, by fight.
    held, event_cost = set(), {}
    for row in positions + [o for o in orders if o.get("side") == "buy"]:
        event = event_of(row.get("market"))
        if event is None:
            continue
        held.add(event)
        price = row.get("average_cost") if "average_cost" in row else row.get("limit_price")
        event_cost[event] = event_cost.get(event, 0.0) + num(row.get("quantity"), 0.0) * num(price, 0.0)

    refused = [row for row in listed(ctx.get("recent_order_outcomes"))
               if row.get("status") == "refused" and "post-only" in str(row.get("reason") or "")]
    real = int(num(ctx.get("rung"), 0.0) or 0) >= 2
    floor = max(knob("min_price"), LONGSHOT_FLOOR_REAL if real else LONGSHOT_FLOOR)
    cash = num(ctx.get("cash"), 0.0)
    reserved = sum(num(o.get("quantity"), 0.0) * num(o.get("limit_price"), 0.0) for o in orders if o.get("side") == "buy")
    free = [max(0.0, (cash - reserved) * 0.98)]  # 2% headroom for fees
    limits = table(ctx.get("limits"))
    equity = num(ctx.get("equity"), cash)
    remaining = table(table(ctx.get("event_risk")).get("remaining_by_market_usd"))

    def budget(ticker):
        room = [knob("ticket_usd"), free[0], num(limits.get("max_order_usd"), knob("ticket_usd")),
                num(limits.get("max_position_usd"), knob("ticket_usd")), MAX_EVENT_SHARE * equity - event_cost.get(event_of(ticker), 0.0)]
        if num(remaining.get(ticker)) is not None:
            room.append(num(remaining.get(ticker)))
        return max(0.0, min(room))

    def size(ticker, price, maker):
        """Whole contracts at `price` within the budget whose cost AND fee fit the free cash: a taker's
        fee is up to 4.9 cents a dollar at the 30-cent floor, more than the 2% headroom holds. None at
        a price under a tick (a sub-penny quote's NO side rounds to 0.00)."""
        if not price >= TICK - EPS:
            return 0
        count = int(budget(ticker) / price + EPS)
        while count > 0 and count * price + fee(series_of(ticker), count, price, maker, rate) > free[0] + EPS:
            count -= 1
        return count

    # Resting bids the fair, the lines or the clock no longer support.
    for order in bids:
        ticker = str(order.get("market") or "").upper()
        if str(order["order_id"]) in cancels or ticker not in shown:
            continue
        entry = priced.get(ticker)
        if entry is None:
            cancels.append(str(order["order_id"]))  # its fight is unmatched, starting, stale or unpriced now
            continue
        leg, price = str(order.get("leg") or "yes"), num(order.get("limit_price"), 0.0)
        count = max(1, int(num(order.get("quantity"), 1.0)))
        edge = (entry[2] if leg == "yes" else 1.0 - entry[2]) - price - fee(entry[1]["series"], count, price, True, rate) / count
        sent, then = when(order.get("submitted_at")), priced_at.get(ticker)
        if then is not None and abs(entry[2] - then) >= knob("requote_move") - EPS:
            cancels.append(str(order["order_id"]))
        elif edge < knob("min_edge") / 2.0:
            cancels.append(str(order["order_id"]))
        elif sent is not None and (now - sent).total_seconds() > 60.0 * knob("requote_minutes"):
            better = best_entry(entry[0], entry[1], entry[2], lambda px, maker, t=ticker: size(t, px, maker), p, rate, floor, False)
            if better is not None and (better[1] != leg or abs(better[2] - price) > EPS):
                cancels.append(str(order["order_id"]))

    # New entries, best edge first: one market a fight.
    offers = []
    for ticker, (market, parsed, fair) in priced.items():
        if parsed["event"] in held:
            continue
        takers = not refused
        entry = best_entry(market, parsed, fair, lambda px, maker, t=ticker: size(t, px, maker), p, rate, floor, takers)
        if entry is not None:
            offers.append((entry[0], ticker, entry, parsed, fair))
    offers.sort(key=lambda row: (-round(row[0], 6), row[1]))  # a tie (a fight's two sides) goes to the first ticker
    intents = []
    for edge, ticker, (_, leg, price, post_only), parsed, fair in offers:
        if len(intents) >= min(int(knob("max_new")), MAX_INTENTS):
            break
        if parsed["event"] in held:
            continue
        quantity = size(ticker, price, post_only)
        if quantity < 1 or quantity * price < 1.0:
            continue
        free[0] -= quantity * price + fee(parsed["series"], quantity, price, post_only, rate)
        held.add(parsed["event"])
        event_cost[parsed["event"]] = event_cost.get(parsed["event"], 0.0) + quantity * price
        starts[parsed["event"]] = fights[parsed["event"]]["start"]
        priced_at[ticker] = round(fair, 4)
        intent = {"market": ticker, "leg": leg, "side": "buy", "quantity": quantity, "type": "limit", "limit_price": price,
                  "reason": (f"The sportsbook moneyline prices '{parsed['team']} wins' at {fair:.3f} for YES; {leg.upper()} at "
                             f"{price:.2f} {'rests as a maker bid' if post_only else 'takes the ask'} and clears the fee by "
                             f"{edge * 100:.1f} cents a contract. Held to settlement.")}
        if post_only:
            intent["post_only"] = True
        intents.append(intent)

    # Keep the start of every fight still bid on, and the fair each resting bid was priced at.
    live = {event_of(o.get("market")) for o in bids if str(o["order_id"]) not in cancels} | {event_of(i["market"]) for i in intents}
    for event in live:
        if event in fights and event not in starts:
            starts[event] = fights[event]["start"]
    resting = {str(o.get("market") or "").upper() for o in bids if str(o["order_id"]) not in cancels} | {i["market"] for i in intents}
    memory = {"starts": {event: starts[event] for event in sorted(live) if starts.get(event)},
              "fair": {ticker: priced_at[ticker] for ticker in sorted(resting) if priced_at.get(ticker) is not None}}

    sports = "/".join(sorted({rows[0][1]["league"].upper() for rows in events.values()})) or "No fight"
    best = f"best edge {offers[0][0] * 100:.1f}c on {offers[0][1]}" if offers else "no edge cleared the fee and margin"
    missed = ", ".join(f"{count} {why}" for why, count in sorted(skipped.items())) or "none skipped"
    thought = (f"{sports}: priced {len(priced)} of {len(markets)} markets on {len(fights)} matched fights ({missed}); {best}. "
               f"Placed {len(intents)} bids and cancelled {len(cancels)}.")
    return {"intents": intents, "cancels": cancels, "thought": thought, "memory": {k: v for k, v in memory.items() if v}}
