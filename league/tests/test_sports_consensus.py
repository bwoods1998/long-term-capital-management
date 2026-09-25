"""The sports-consensus founders (K1 of the Kalshi-scale run, Sept 25, 2026): Kalshi's game markets
priced from the sportsbook line the `odds` feed records, bid where Kalshi is off it by more than the
fee and a margin.

The slate these tests read is this weekend's, recorded live on the morning of Sept 25, 2026
(fixtures/sports_consensus_slate_20260925.json.gz): every NFL, NCAAF, MLB, MLS and Liga MX game on
ESPN's boards as the `sports` feed shows them, every open Kalshi GAME/SPREAD/TOTAL market of those
leagues for Sept 25-28 as `ctx["markets"]` shows them, and DraftKings' lines (the only provider ESPN
answered) for one game a league. They hold the matcher to the rule that matters most -- a market is
priced only when its game is found without guessing -- and measure it: every Kalshi event of the
weekend matched but three MLB games: two ESPN no longer lists at the first pitch Kalshi names, and one
named without its game number on a doubleheader day (the review of Sept 25, 2026: either game, so neither).
"""

from __future__ import annotations

import copy
import gzip
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from league import niches, parameters, runner, seeds
from league.safety import check_code
from league.tests.test_seeds import SeedCase

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sports_consensus_slate_20260925.json.gz"
SLATE = json.loads(gzip.decompress(FIXTURE.read_bytes()).decode("utf-8"))["leagues"]
SERIES = {"nfl": ["KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL"], "ncaaf": ["KXNCAAFGAME", "KXNCAAFSPREAD", "KXNCAAFTOTAL"],
          "mlb": ["KXMLBGAME", "KXMLBSPREAD", "KXMLBTOTAL"], "mls": ["KXMLSGAME"], "ligamx": ["KXLIGAMXGAME"]}
WEEKEND = ("26SEP25", "26SEP26", "26SEP27", "26SEP28")
# The one game a league whose lines were recorded (ESPN's id, Kalshi's code), and a moment before it starts.
GAMES = {"nfl": ("401872953", "26SEP27LACBUF", "2026-09-27T12:00:00.000Z"), "ncaaf": ("401862779", "26SEP25ARMYTEM", "2026-09-25T15:00:00.000Z"),
         "mlb": ("401817074", "26SEP251805CHCBOSG2", "2026-09-25T18:00:00.000Z"), "mls": ("761830", "26SEP26ATLNYC", "2026-09-26T12:00:00.000Z")}


def module() -> dict:
    """The seed's module namespace, run as the runner runs it (for its helpers)."""
    namespace: dict = {"__name__": "strategy"}
    exec(compile(seeds.load("consensus-nfl"), "strategy.py", "exec"), namespace)  # noqa: S102 - the seed passed check_code
    return namespace


SEED = module()


def founder(league: str) -> dict:
    return next(f for f in niches.load()["kalshi-sports"].founders if f["key"] == f"consensus-{league}")


def code_for(league: str) -> str:
    desk = niches.load()["kalshi-sports"]
    return niches.founder_code(seeds.load(f"consensus-{league}"), desk, founder(league))


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def odds_row(league: str, fetched: str, lines: dict | None = None) -> dict:
    """The `odds` feed's league row: every recorded game of the slate with its lines and when they were fetched."""
    board = {g["id"]: g for g in SLATE[league]["board"]}
    events = []
    for gid, recorded in (lines if lines is not None else SLATE[league]["odds"]).items():
        game = board[gid]
        events.append({"id": gid, "name": game["name"], "start": game["start"], "home": game["home"]["team"],
                       "away": game["away"]["team"], "fetched": fetched, **copy.deepcopy(recorded)})
    return {"t": fetched, "league": league, "events": events}


def ctx_for(league: str, now: str, *, markets=None, lines=None, fetched=None, **over) -> dict:
    ctx = {"now": now, "venue": "kalshi", "rung": 1, "params": dict(founder(league).get("params") or {}), "memory": {},
           "cash": 200.0, "equity": 200.0, "limits": {"max_position_usd": 20.0, "max_order_usd": 20.0},
           "fees": {"crypto_taker": 0.0025, "crypto_maker": 0.0015, "kalshi_taker_rate": 0.07}, "positions": [], "open_orders": [],
           "recent_order_outcomes": [],
           "markets": copy.deepcopy(markets if markets is not None else [m for m in SLATE[league]["markets"] if m["series"] in SERIES[league]]),
           "feeds": {"sports": {league: {"t": now, "league": league, "events": copy.deepcopy(SLATE[league]["board"])}},
                     "odds": {league: odds_row(league, fetched or now, lines)}}}
    ctx.update(over)
    return ctx


def game_markets(league: str, code: str, series: str | None = None) -> list:
    return [m for m in SLATE[league]["markets"] if m["market"].split("-")[1] == code and (series is None or m["series"] == series)]


def market(ticker: str, bid: float, ask: float, title: str, strike=None) -> dict:
    return {"market": ticker, "series": ticker.split("-")[0], "title": title, "strike": strike, "yes_bid": bid, "yes_ask": ask,
            "hours_to_close": 20.0, "hours_to_resolve": 20.0, "volume_24h": 1000.0}


class Matching(unittest.TestCase):
    """A market is priced only when exactly one game on the board is the game its ticker names."""

    def measure(self, league: str) -> dict:
        board = SEED["prepare"](SLATE[league]["board"])
        parsed_rows, learned = [], {}
        for row in SLATE[league]["markets"]:
            parsed = SEED["parse_market"](row)
            self.assertIsNotNone(parsed, row["market"])  # every market of the weekend reads
            parsed_rows.append((row, parsed))
            if parsed["name"] and parsed["team"] not in (None, "TIE"):
                learned.setdefault(parsed["game"], {}).setdefault(parsed["team"], set()).add(SEED["words"](parsed["name"]))
        events, matched, games, sides = {}, set(), {}, []
        for row, parsed in parsed_rows:
            events.setdefault(parsed["event"], parsed)
        for event, parsed in events.items():
            hit = SEED["match_game"](parsed, board, learned.get(parsed["game"]) or {})
            if hit is not None:
                matched.add(event)
                games.setdefault(hit[0]["id"], set()).add(parsed["game"])
        for row, parsed in parsed_rows:
            if parsed["kind"] == "GAME" and parsed["team"] != "TIE":
                hit = SEED["match_game"](parsed, board, learned.get(parsed["game"]) or {})
                if hit is not None:
                    sides.append((parsed, hit[0][hit[1][parsed["team"]]]))
        return {"events": set(events), "matched": matched, "games": games, "sides": sides}

    def test_every_weekend_event_is_matched_or_skipped_never_guessed(self):
        expected = {"nfl": (45, 45), "ncaaf": (346, 346), "mlb": (69, 66), "mls": (15, 15), "ligamx": (9, 9)}
        for league, (events, matched) in expected.items():
            with self.subTest(league):
                found = self.measure(league)
                self.assertEqual((len(found["events"]), len(found["matched"])), (events, matched))
                self.assertGreaterEqual(len(found["matched"]) / len(found["events"]), 0.95)
                # One ESPN game is one Kalshi game (its GAME, SPREAD and TOTAL events share the game's code).
                self.assertEqual({gid: keys for gid, keys in found["games"].items() if len(keys) > 1}, {})
                # Every winner market's team is the ESPN side its code resolved to: by the abbreviation, a known
                # Kalshi spelling, or the title naming one of that side's names.
                aliases = SEED["ALIASES"].get(league) or {}
                for parsed, team in found["sides"]:
                    names = SEED["team_names"](team)
                    self.assertTrue(parsed["team"] == team["abbrev"] or parsed["team"] in aliases.get(team["abbrev"], ())
                                    or SEED["words"](parsed["name"]) in names, (parsed["ticker"], team))

    def test_the_unmatched_are_rescheduled_games_and_a_doubleheader_game_without_its_number(self):
        found = self.measure("mlb")
        # Rescheduled into doubleheaders: Kalshi still lists the original 7:10 PM and 7:15 PM games. And BAL-NYY
        # plays twice on Sept 25 (ESPN: 4:05 PM and 7:05 PM, the Sept 26 game moved in): Kalshi's 7:05 PM ticker
        # carries no game number, so it may be either game once the doubleheader is set, and is skipped.
        self.assertEqual(sorted(found["events"] - found["matched"]),
                         ["KXMLBGAME-26SEP251905BALNYY", "KXMLBGAME-26SEP251910CHCBOS", "KXMLBGAME-26SEP261915BALNYY"])
        # Game 2 of CHC-BOS is 6:05 PM on Kalshi and 6:00 PM on ESPN: the same game, within 15 minutes.
        self.assertIn("KXMLBTOTAL-26SEP251805CHCBOSG2", found["matched"])

    def test_a_wrong_match_is_impossible(self):
        board = SLATE["ncaaf"]["board"]
        army = next(g for g in board if g["id"] == "401862779")  # Army at Temple, Sept 25 16:00 New York
        parse = lambda ticker, title="": SEED["parse_market"]({"market": ticker, "title": title})
        match = lambda parsed, games, learned=None: SEED["match_game"](parsed, SEED["prepare"](games), learned or {})
        right = parse("KXNCAAFGAME-26SEP25ARMYTEM-ARMY", "Army wins")
        self.assertEqual(match(right, board)[1], {"ARMY": "away", "TEM": "home"})
        self.assertIsNone(match(parse("KXNCAAFGAME-26SEP26ARMYTEM-ARMY", "Army wins"), board))  # another date
        twice = [army, {**copy.deepcopy(army), "id": "999"}]
        self.assertIsNone(match(right, twice))  # two games of the same teams on the date: skipped
        same = copy.deepcopy(army)
        same["home"]["abbrev"] = "ARMY"
        self.assertIsNone(match(right, [same]))  # a code that fits both sides: skipped
        self.assertIsNone(match(parse("KXNCAAFGAME-26SEP25ARMYTEM-NAVY", "Navy wins"), board))  # a team not in the game
        self.assertIsNone(match(parse("KXNCAAFGAME-26SEP25ARMYXYZ-ARMY", "Army wins"), board))  # a code no side is
        # A title's name counts only when it IS one of a side's names.
        self.assertIsNone(match(parse("KXNCAAFGAME-26SEP25ARMYTMP-TMP", "Temp wins"), board, {"TMP": {"temp"}}))
        self.assertEqual(match(parse("KXNCAAFGAME-26SEP25ARMYTMP-TMP", "Temple wins"), board, {"TMP": {"temple"}})[1],
                         {"ARMY": "away", "TMP": "home"})
        # Baseball names the first pitch: 15 minutes either way is the same game, more is not.
        mlb = SLATE["mlb"]["board"]
        self.assertIsNotNone(match(parse("KXMLBTOTAL-26SEP251805CHCBOSG2-7", "Over 6.5 runs scored"), mlb))
        self.assertIsNone(match(parse("KXMLBTOTAL-26SEP251825CHCBOSG2-7", "Over 6.5 runs scored"), mlb))

    def test_what_a_ticker_and_title_say(self):
        parse = SEED["parse_market"]
        spread = parse({"market": "KXNFLSPREAD-26OCT01PITCLE-PIT8", "title": "PIT Steelers wins by over 7.5 points?", "strike": 7.5})
        self.assertEqual((spread["kind"], spread["date"], spread["teams"], spread["team"], spread["name"], spread["line"]),
                         ("SPREAD", (2026, 10, 1), "PITCLE", "PIT", "PIT Steelers", 7.5))
        total = parse({"market": "KXMLBTOTAL-26SEP251805CHCBOSG2-9", "title": "Over 8.5 runs scored", "strike": 8.5})
        self.assertEqual((total["clock"], total["teams"], total["line"], total["game"]), ("1805", "CHCBOS", 8.5, "mlb:26SEP251805CHCBOSG2"))
        self.assertEqual(parse({"market": "KXNFLTOTAL-26OCT01PITCLE-60", "title": "Full Game: over 59.5 points scored?"})["line"], 59.5)
        self.assertEqual(parse({"market": "KXMLBGAME-26SEP271520BALNYY-NYY", "title": "New York Y wins"})["name"], "New York Y")
        self.assertEqual(parse({"market": "KXMLSGAME-26SEP26ATLNYC-TIE", "title": "Tie is the result"})["team"], "TIE")
        self.assertIsNone(parse({"market": "KXNFLGAME-26SEP27LACBUF-TIE", "title": "Tie"}))  # a tie is soccer's only
        self.assertIsNone(parse({"market": "KXNFLSPREAD-26OCT01PITCLE-PIT8", "title": "PIT Steelers wins by over 7.5 points?", "strike": 8.5}))
        self.assertIsNone(parse({"market": "KXNFL1HSPREAD-26OCT01PITCLE-PIT4", "title": "x"}))  # not a series it prices
        self.assertEqual(SEED["words"]("Arkansas St."), "arkansas state")
        self.assertEqual(SEED["words"]("St. Louis CITY SC"), "saint louis city sc")
        self.assertEqual(SEED["words"]("León"), "leon")


class Pricing(unittest.TestCase):
    """What the book's line says each market is worth."""

    def fair(self, league, ticker, lines=None, params=None):
        """The fair YES of one market, as `decide` prices it."""
        row = next(m for m in SLATE[league]["markets"] if m["market"] == ticker)
        parsed = SEED["parse_market"](row)
        board = SEED["prepare"](SLATE[league]["board"])
        learned = {}
        for m in SLATE[league]["markets"]:
            p = SEED["parse_market"](m)
            if p["game"] == parsed["game"] and p["name"] and p["team"] not in (None, "TIE"):
                learned.setdefault(p["team"], set()).add(SEED["words"](p["name"]))
        event, sides = SEED["match_game"](parsed, board, learned)
        recorded = (lines or SLATE[league]["odds"])[event["id"]]
        p = {**SEED["PARAMS"], **(founder(league).get("params") or {}), **(params or {})}
        model, why = SEED["game_model"](SEED["consensus"](recorded, parsed["sport"]), {**event, "win_probability": recorded.get("win_probability")},
                                        parsed["sport"], p)
        if model is None:
            return why
        return SEED["fair_yes"](parsed, sides, model, p)

    def test_a_winner_is_the_de_vigged_moneyline_and_the_predictor_only_by_weight(self):
        line = SLATE["nfl"]["odds"]["401872953"]["lines"][0]  # LAC at BUF, Draft Kings: BUF -325, LAC +260
        self.assertEqual((line["home_ml"], line["away_ml"], line["implied_home"]), (-325, 260, 0.7335))
        self.assertAlmostEqual(self.fair("nfl", "KXNFLGAME-26SEP27LACBUF-BUF"), 0.7335)
        self.assertAlmostEqual(self.fair("nfl", "KXNFLGAME-26SEP27LACBUF-LAC"), 1 - 0.7335)
        predicted = SLATE["nfl"]["odds"]["401872953"]["win_probability"]["home"]
        self.assertAlmostEqual(self.fair("nfl", "KXNFLGAME-26SEP27LACBUF-BUF", params={"predictor_weight": 0.5}),
                               0.5 * 0.7335 + 0.5 * predicted)

    def test_a_football_spread_is_skipped_across_a_key_number_and_priced_inside_one(self):
        # BUF -7: an integer line on the key number 7 (a push), so every BUF-LAC spread strike is skipped.
        for row in game_markets("nfl", "26SEP27LACBUF", "KXNFLSPREAD"):
            self.assertIsNone(self.fair("nfl", row["market"]), row["market"])
        # Army -5.5 at even money, moneyline in step (Army 63.9%): strikes between the key numbers 3 and 7 are priced.
        lines = copy.deepcopy(SLATE["ncaaf"]["odds"])
        line = lines["401862779"]["lines"][0]
        line.update(spread=5.5, implied_home_cover=0.5, implied_home=0.361, details="ARMY -5.5")
        fair = {row["market"].rsplit("-", 1)[1]: self.fair("ncaaf", row["market"], lines=lines)
                for row in game_markets("ncaaf", "26SEP25ARMYTEM", "KXNCAAFSPREAD")}
        self.assertAlmostEqual(fair["ARMY6"], 0.5)  # the book's own line: its de-vigged cover
        self.assertAlmostEqual(fair["ARMY4"], 1 - SEED["NORMAL"].cdf((3.5 - 5.5) / 15.5))
        self.assertAlmostEqual(fair["ARMY7"], 1 - SEED["NORMAL"].cdf((6.5 - 5.5) / 15.5))
        self.assertEqual((fair["ARMY3"], fair["ARMY8"]), (None, None))  # 3 and 7 lie between them and the line
        self.assertTrue(all(value is None for key, value in fair.items() if key.startswith("TEM")))  # -3 lies between
        # A spread the moneyline contradicts is not priced at all.
        line.update(implied_home=0.60)
        self.assertEqual(self.fair("ncaaf", "KXNCAAFGAME-26SEP25ARMYTEM-ARMY", lines=lines), "spread and moneyline disagree")

    def test_a_total_at_the_line_is_the_de_vigged_over_and_strikes_near_it_follow_the_curve(self):
        line = SLATE["nfl"]["odds"]["401872953"]["lines"][0]
        self.assertEqual((line["over_under"], line["implied_over"]), (50.5, 0.4892))
        self.assertAlmostEqual(self.fair("nfl", "KXNFLTOTAL-26SEP27LACBUF-51"), 0.4892)
        mu = 50.5 + 13.5 * SEED["NORMAL"].inv_cdf(0.4892)
        self.assertAlmostEqual(self.fair("nfl", "KXNFLTOTAL-26SEP27LACBUF-48"), 1 - SEED["NORMAL"].cdf((47.5 - mu) / 13.5))
        self.assertIsNone(self.fair("nfl", "KXNFLTOTAL-26SEP27LACBUF-60"))  # 59.5 is 9.4 points out: past half a sigma

    def test_baseball_spreads_only_at_the_run_line_and_totals_near_the_line(self):
        # CHC at BOS, game 2: BOS +1.5 at -182, CHC -1.5 at +150. Kalshi's "Chicago C wins by over 1.5" is the run line.
        self.assertAlmostEqual(self.fair("mlb", "KXMLBSPREAD-26SEP251805CHCBOSG2-CHC2"), 1 - 0.6174)
        for other in ("CHC3", "CHC4", "BOS2", "BOS3"):
            self.assertIsNone(self.fair("mlb", f"KXMLBSPREAD-26SEP251805CHCBOSG2-{other}"), other)
        self.assertAlmostEqual(self.fair("mlb", "KXMLBTOTAL-26SEP251805CHCBOSG2-7"), 0.4892)  # over 6.5: the book's own
        self.assertIsNone(self.fair("mlb", "KXMLBTOTAL-26SEP251805CHCBOSG2-4"))  # over 3.5: runs are skewed; not priced

    def test_soccer_is_the_three_way_de_vig_with_the_draw(self):
        self.assertAlmostEqual(self.fair("mls", "KXMLSGAME-26SEP26ATLNYC-ATL"), 0.4189)
        self.assertAlmostEqual(self.fair("mls", "KXMLSGAME-26SEP26ATLNYC-NYC"), 0.3178)
        self.assertAlmostEqual(self.fair("mls", "KXMLSGAME-26SEP26ATLNYC-TIE"), 0.2633)
        lines = copy.deepcopy(SLATE["mls"]["odds"])
        lines["761830"]["lines"][0].update(draw_ml=None, implied_draw=None)
        self.assertEqual(self.fair("mls", "KXMLSGAME-26SEP26ATLNYC-TIE", lines=lines), "no three-way price")

    def test_the_fee_is_the_books(self):
        fee = SEED["fee"]
        self.assertEqual(fee("KXNFLGAME", 10, 0.53, True, 0.07), 0.0436)  # a quarter of the taker rate, up to $0.0001
        self.assertEqual(fee("KXNFLGAME", 10, 0.53, False, 0.07), 0.1744)
        self.assertEqual(fee("KXMLBTOTAL", 10, 0.5, True, 0.07), 0.0)  # MLB totals charge makers nothing
        # ctx carries no series multiplier, so a baseball taker is priced at the full rate unless fee_multiplier says 0.5.
        self.assertEqual(fee("KXMLBTOTAL", 10, 0.5, False, 0.07), 0.175)
        self.assertEqual(fee("KXMLBTOTAL", 10, 0.5, False, 0.07 * 0.5), 0.0875)
        self.assertEqual(fee("KXMLBGAME", 10, 0.5, True, 0.07), 0.0438)
        self.assertEqual(fee("KXMLSGAME", 10, 0.5, True, 0.07), 0.0)
        self.assertEqual(fee("KXNFLGAME", 1, 0.5, False, 0.07), 0.0175)
        self.assertEqual(SEED["PARAMS"]["fee_multiplier"], 1.0)


class Entries(SeedCase):
    SEED = "consensus-nfl"
    NOW = "2026-09-27T12:00:00.000Z"  # LAC at BUF kicks off at 17:00Z
    BUF = "KXNFLGAME-26SEP27LACBUF-BUF"

    def run_seed(self, ctx, seed=None):
        out = runner.decide(code_for("nfl"), ctx)
        self.assertTrue(out.get("ok"), out.get("error"))
        self._check(out, ctx)
        return out

    def ctx(self, *rows, **over):
        rows = rows or (market(self.BUF, 0.60, 0.70, "Buffalo wins"), market("KXNFLGAME-26SEP27LACBUF-LAC", 0.30, 0.40, "Los Angeles C wins"))
        return ctx_for("nfl", over.pop("now", self.NOW), markets=list(rows), **over)

    def test_a_maker_bid_a_tick_over_the_best_bid_where_it_clears_the_edge(self):
        out = self.run_seed(self.ctx())
        self.assertEqual(len(out["intents"]), 1)
        intent = out["intents"][0]
        self.assertEqual((intent["market"], intent["leg"], intent["limit_price"], intent.get("post_only"), intent["type"]),
                         (self.BUF, "yes", 0.61, True, "limit"))
        self.assertEqual(intent["quantity"], int(10.0 / 0.61))  # ticket_usd $10
        self.assertIn("NFL: priced 2 of 2 markets on 1 matched games", out["thought"])
        self.assertEqual(out["memory"], {"starts": {"KXNFLGAME-26SEP27LACBUF": "2026-09-27T17:00:00Z"}, "fair": {self.BUF: 0.7335}})

    def test_it_joins_the_bid_when_a_tick_over_no_longer_clears_the_fee(self):
        lines = copy.deepcopy(SLATE["nfl"]["odds"])
        lines["401872953"]["lines"][0].update(implied_home=0.50, spread=-0.5, implied_home_cover=0.49)
        out = self.run_seed(self.ctx(market(self.BUF, 0.48, 0.52, "Buffalo wins"), lines=lines))
        # At 0.49 the edge is 1c less the maker fee (0.4c): under 1.2c. At the bid, 0.48, it is 1.6c.
        self.assertEqual([(i["leg"], i["limit_price"]) for i in out["intents"]], [("yes", 0.48)])

    def test_a_taker_entry_where_the_edge_after_the_taker_fee_is_large_and_post_only_once_refused(self):
        out = self.run_seed(self.ctx(market(self.BUF, 0.55, 0.62, "Buffalo wins")))
        self.assertEqual([(i["leg"], i["limit_price"], i.get("post_only")) for i in out["intents"]], [("yes", 0.62, None)])
        refused = [{"at": self.NOW, "instrument": {"market_id": self.BUF}, "status": "refused", "submitted_to_venue": False,
                    "reason": "a real entry on sports-consensus-nfl must be a post-only limit until the family's pooled taker record "
                              "is positive (0 taker settlements): send a limit with post_only, which rests or is refused"}]
        out = self.run_seed(self.ctx(market(self.BUF, 0.55, 0.62, "Buffalo wins"), recent_order_outcomes=refused))
        self.assertEqual([(i["leg"], i["limit_price"], i.get("post_only")) for i in out["intents"]], [("yes", 0.56, True)])

    def test_one_market_an_event_and_one_a_game(self):
        held = [{"market": self.BUF, "leg": "yes", "quantity": 5.0, "average_cost": 0.6, "mark": 0.6}]
        total = market("KXNFLTOTAL-26SEP27LACBUF-51", 0.30, 0.40, "Full Game: over 50.5 points scored?", 50.5)
        out = self.run_seed(self.ctx(market(self.BUF, 0.60, 0.70, "Buffalo wins"), market("KXNFLGAME-26SEP27LACBUF-LAC", 0.2, 0.25, "Los Angeles C wins"),
                                     total, positions=held))
        self.assertEqual(out["intents"], [])  # the event is held, and so is the game (max_per_game 1)
        ctx = self.ctx(market(self.BUF, 0.60, 0.70, "Buffalo wins"), total, positions=held)
        ctx["params"]["max_per_game"] = 2
        out = self.run_seed(ctx)
        self.assertEqual([i["market"] for i in out["intents"]], ["KXNFLTOTAL-26SEP27LACBUF-51"])  # the total is another event

    def test_stale_lines_a_game_about_to_start_and_absent_feeds_buy_nothing(self):
        stale = self.run_seed(self.ctx(fetched="2026-09-27T10:00:00.000Z"))
        self.assertEqual(stale["intents"], [])
        self.assertIn("1 stale lines", stale["thought"])
        starting = self.run_seed(self.ctx(now="2026-09-27T16:45:00.000Z"))
        self.assertEqual(starting["intents"], [])
        self.assertIn("1 starting", starting["thought"])
        for feeds in (None, {}, {"sports": {}}, {"odds": {"nfl": {}}, "sports": {"nfl": {}}}):
            ctx = self.ctx()
            if feeds is None:
                ctx.pop("feeds")
            else:
                ctx["feeds"] = feeds
            out = self.run_seed(ctx)
            self.assertEqual(out["intents"], [], feeds)
            self.assertTrue(out["thought"])

    def test_sizing_follows_the_tightest_room_and_real_money_skips_longshots(self):
        ctx = self.ctx(event_risk={"remaining_by_market_usd": {self.BUF: 2.0}})
        self.assertEqual(self.run_seed(ctx)["intents"][0]["quantity"], 3)  # $2 of room at 61 cents
        ctx = self.ctx(limits={"max_position_usd": 6.0, "max_order_usd": 6.0})
        self.assertEqual(self.run_seed(ctx)["intents"][0]["quantity"], 9)
        # LAC bid 0.20, asked 0.30, against a fair of 0.2665: on practice a YES bid at 0.21 (5.4c of edge). On real
        # money nothing under 30 cents is entered, so the NO side (fair 0.7335) is bid at 0.71 instead.
        lac = market("KXNFLGAME-26SEP27LACBUF-LAC", 0.20, 0.30, "Los Angeles C wins")
        practice = self.run_seed(self.ctx(lac))
        self.assertEqual([(i["leg"], i["limit_price"]) for i in practice["intents"]], [("yes", 0.21)])
        real = self.run_seed(self.ctx(lac, rung=2))
        self.assertEqual([(i["leg"], i["limit_price"]) for i in real["intents"]], [("no", 0.71)])

    def test_at_most_max_new_orders_a_wake(self):
        ctx = ctx_for("ncaaf", "2026-09-25T15:00:00.000Z")
        lines = copy.deepcopy(SLATE["ncaaf"]["odds"])
        ctx["feeds"]["odds"]["ncaaf"] = odds_row("ncaaf", ctx["now"], lines)
        ctx["markets"] = [market("KXNCAAFTOTAL-26SEP25ARMYTEM-47", 0.40, 0.60, "Over 46.5 points scored", 46.5),
                          market("KXNCAAFTOTAL-26SEP25ARMYTEM-49", 0.30, 0.60, "Over 48.5 points scored", 48.5)]
        ctx["params"].update(max_per_game=3, max_new=1)
        out = runner.decide(code_for("ncaaf"), ctx)
        self.assertEqual(len(out["intents"]), 1)


class Cancels(Entries):
    SENT = "2026-09-27T11:50:00.000Z"

    def order(self, price=0.61, sent=None, ticker=None, leg="yes"):
        return {"order_id": "ord-1", "market": ticker or self.BUF, "leg": leg, "side": "buy", "quantity": 16.0, "limit_price": price,
                "filled": 0.0, "submitted_at": sent or self.SENT}

    def test_a_resting_bid_the_line_still_supports_is_kept(self):
        ctx = self.ctx(market(self.BUF, 0.61, 0.70, "Buffalo wins"), open_orders=[self.order()],
                       memory={"starts": {"KXNFLGAME-26SEP27LACBUF": "2026-09-27T17:00:00Z"}, "fair": {self.BUF: 0.7335}})
        out = self.run_seed(ctx)
        self.assertEqual((out["cancels"], out["intents"]), ([], []))
        self.assertEqual(out["memory"]["fair"], {self.BUF: 0.7335})

    def test_a_bid_is_cancelled_at_the_start_even_when_its_market_is_not_shown(self):
        ctx = self.ctx(market("KXNFLGAME-26SEP27TENNYG-NYG", 0.4, 0.5, "New York G wins"), open_orders=[self.order()],
                       memory={"starts": {"KXNFLGAME-26SEP27LACBUF": "2026-09-27T17:00:00Z"}}, now="2026-09-27T16:45:00.000Z")
        self.assertEqual(self.run_seed(ctx)["cancels"], ["ord-1"])
        del ctx["feeds"]  # and when the feeds cannot be read
        self.assertEqual(self.run_seed(ctx)["cancels"], ["ord-1"])

    def test_a_bid_is_cancelled_when_the_line_moves(self):
        ctx = self.ctx(market(self.BUF, 0.61, 0.70, "Buffalo wins"), open_orders=[self.order()], memory={"fair": {self.BUF: 0.72}})
        self.assertEqual(self.run_seed(ctx)["cancels"], ["ord-1"])  # 0.72 -> 0.7335: the fair moved 1.35 cents

    def test_a_bid_whose_edge_is_gone_is_cancelled(self):
        ctx = self.ctx(market(self.BUF, 0.73, 0.75, "Buffalo wins"), open_orders=[self.order(price=0.73)])
        self.assertEqual(self.run_seed(ctx)["cancels"], ["ord-1"])

    def test_an_old_bid_is_requoted_when_a_better_price_is_due(self):
        stale = self.order(price=0.58, sent="2026-09-27T10:30:00.000Z")
        ctx = self.ctx(market(self.BUF, 0.62, 0.70, "Buffalo wins"), open_orders=[stale])
        self.assertEqual(self.run_seed(ctx)["cancels"], ["ord-1"])
        fresh = self.order(price=0.58, sent=self.SENT)
        self.assertEqual(self.run_seed(self.ctx(market(self.BUF, 0.62, 0.70, "Buffalo wins"), open_orders=[fresh]))["cancels"], [])

    def test_a_bid_on_a_game_that_can_no_longer_be_priced_is_cancelled(self):
        ctx = self.ctx(open_orders=[self.order()], fetched="2026-09-27T10:00:00.000Z")
        self.assertEqual(self.run_seed(ctx)["cancels"], ["ord-1"])


def synthetic(count: int, now: str, start: str = "2026-09-26T19:00:00Z") -> tuple:
    """`count` college games of one Saturday, each with a fresh DraftKings winner line (home 0.60) and a
    winner market bid 0.50 / asked 0.56: (board, odds row, markets)."""
    board, events, rows = [], [], []
    for i in range(count):
        tag = chr(65 + i // 26) + chr(65 + i % 26)
        home, away = f"HOME{tag}", f"AWAY{tag}"
        board.append({"id": f"9{i:03d}", "name": f"{away} at {home}", "start": start, "status": "pre",
                      "home": {"team": f"Home {tag}", "abbrev": home, "location": f"Home {tag}", "nickname": "H"},
                      "away": {"team": f"Away {tag}", "abbrev": away, "location": f"Away {tag}", "nickname": "A"}})
        events.append({"id": f"9{i:03d}", "start": start, "fetched": now, "win_probability": None,
                       "lines": [{"provider": "Draft Kings", "home_ml": -150, "away_ml": 130, "implied_home": 0.6, "draw_ml": None}]})
        rows.append(market(f"KXNCAAFGAME-26SEP26{away}{home}-{home}", 0.50, 0.56, f"Home {tag} wins"))
    return board, {"t": now, "league": "ncaaf", "events": events}, rows


class ReviewMatching(unittest.TestCase):
    """The review of Sept 25, 2026: adversarial pairs the matcher refuses rather than guesses."""

    def parse(self, ticker, title=""):
        return SEED["parse_market"]({"market": ticker, "title": title})

    def match(self, parsed, games, learned=None):
        return SEED["match_game"](parsed, SEED["prepare"](games), learned or {})

    def test_a_doubleheader_game_is_named_by_its_number_or_not_at_all(self):
        mlb = SLATE["mlb"]["board"]  # CHC at BOS twice on Sept 25: 1:05 PM (401817104) and 6:00 PM (401817074)
        self.assertEqual(self.match(self.parse("KXMLBGAME-26SEP251805CHCBOSG2-CHC"), mlb)[0]["id"], "401817074")
        self.assertEqual(self.match(self.parse("KXMLBGAME-26SEP251305CHCBOSG1-CHC"), mlb)[0]["id"], "401817104")
        # Without its number, even at the exact first pitch of one of them: either game, so neither.
        self.assertIsNone(self.match(self.parse("KXMLBGAME-26SEP251800CHCBOS-CHC"), mlb))
        self.assertIsNone(self.match(self.parse("KXMLBGAME-26SEP251305CHCBOS-CHC"), mlb))
        # One game of the pair that day: its first pitch names it.
        self.assertEqual(self.match(self.parse("KXMLBGAME-26SEP261915CHCBOS-CHC"), mlb)[0]["id"], "401817089")

    def test_prefix_codes_and_a_shared_location(self):
        def team(abbrev, name, location, nickname):
            return {"team": name, "abbrev": abbrev, "location": location, "short": location, "nickname": nickname}
        game = {"id": "1", "start": "2026-09-26T16:00:00Z", "status": "pre",
                "home": team("MIA", "Miami Hurricanes", "Miami", "Hurricanes"),
                "away": team("M-OH", "Miami (OH) RedHawks", "Miami (OH)", "RedHawks")}
        words = SEED["words"]
        learned = {"MIAOH": {words("Miami (OH)")}, "MIA": {words("Miami")}}
        hit = self.match(self.parse("KXNCAAFGAME-26SEP26MIAOHMIA-MIAOH", "Miami (OH) wins"), [game], learned)
        self.assertEqual(hit[1], {"MIAOH": "away", "MIA": "home"})  # YES on -MIAOH is the away side
        self.assertEqual(self.match(self.parse("KXNCAAFGAME-26SEP26MIAOHMIA-MIA", "Miami wins"), [game], learned)[1]["MIA"], "home")
        # A title that names the other Miami on the -MIAOH market makes both codes one side: skipped.
        self.assertIsNone(self.match(self.parse("KXNCAAFGAME-26SEP26MIAOHMIA-MIA"), [game], {"MIAOH": {"miami"}, "MIA": {"miami"}}))
        # OHST and OH: one a prefix of the other, read in either order and only one way.
        ohio = {"id": "2", "start": "2026-09-26T16:00:00Z", "status": "pre",
                "home": team("OHST", "Ohio State Buckeyes", "Ohio State", "Buckeyes"), "away": team("OH", "Ohio Bobcats", "Ohio", "Bobcats")}
        self.assertEqual(self.match(self.parse("KXNCAAFGAME-26SEP26OHOHST-OH"), [game, ohio])[1], {"OH": "away", "OHST": "home"})
        self.assertEqual(self.match(self.parse("KXNCAAFGAME-26SEP26OHSTOH-OH"), [game, ohio])[1], {"OH": "away", "OHST": "home"})
        # A team string that splits two ways (A|BC and AB|C) is two readings: skipped.
        split = {"id": "3", "start": "2026-09-26T16:00:00Z", "status": "pre",
                 "home": team("AB", "Ab Team", "Ab", "Ab"), "away": team("C", "C Team", "Cee", "C")}
        self.assertIsNone(self.match(self.parse("KXNCAAFGAME-26SEP26ABC-AB"), [split], {"A": {words("Ab")}, "BC": {words("Cee")}}))

    def test_two_kalshi_games_read_as_one_board_game_are_neither(self):
        now = "2026-09-25T18:00:00.000Z"  # game 2 of CHC-BOS starts at 22:00Z
        g2 = market("KXMLBGAME-26SEP251805CHCBOSG2-CHC", 0.40, 0.46, "Chicago C wins")
        out = runner.decide(code_for("mlb"), ctx_for("mlb", now, markets=[g2]))
        self.assertEqual([i["market"] for i in out["intents"]], [g2["market"]])
        # A second Kalshi game whose first pitch is also within 15 minutes of ESPN's 6:00 PM game.
        g1 = market("KXMLBGAME-26SEP251810CHCBOSG1-CHC", 0.40, 0.46, "Chicago C wins")
        out = runner.decide(code_for("mlb"), ctx_for("mlb", now, markets=[g2, g1]))
        self.assertEqual(out["intents"], [])
        self.assertIn("2 ambiguous", out["thought"])


class ReviewMoney(SeedCase):
    """The review of Sept 25, 2026: money rules that must hold whatever the wake shows."""

    SEED, NOW, BUF = Entries.SEED, Entries.NOW, Entries.BUF
    run_seed, ctx = Entries.run_seed, Entries.ctx

    TOTAL = "KXNFLTOTAL-26SEP27LACBUF-48"  # over 47.5: fair 0.5774 on the recorded line
    STARTS = {"KXNFLTOTAL-26SEP27LACBUF": "2026-09-27T17:00:00Z"}

    def bid(self, ticker, oid="ord-1", price=0.50, leg="yes"):
        return {"order_id": oid, "market": ticker, "leg": leg, "side": "buy", "quantity": 16.0, "limit_price": price,
                "filled": 0.0, "submitted_at": "2026-09-27T11:50:00.000Z"}

    def test_every_resting_bid_goes_when_the_lines_or_the_board_are_absent(self):
        for drop in ("odds", "sports", None):
            ctx = self.ctx(open_orders=[self.bid(self.BUF, price=0.61)], memory={"fair": {self.BUF: 0.7335}})
            if drop is None:
                del ctx["feeds"]
            else:
                del ctx["feeds"][drop]
            self.assertEqual(self.run_seed(ctx)["cancels"], ["ord-1"], drop)

    def test_a_bid_whose_market_is_not_shown_is_judged_by_its_own_ticker(self):
        memory = {"starts": self.STARTS, "fair": {self.TOTAL: 0.5774}}
        kept = self.run_seed(self.ctx(open_orders=[self.bid(self.TOTAL)], memory=memory))  # the winners shown, not the total
        self.assertEqual(kept["cancels"], [])
        self.assertEqual(kept["memory"]["fair"], {self.TOTAL: 0.5774})
        moved = self.run_seed(self.ctx(open_orders=[self.bid(self.TOTAL)], memory={"starts": self.STARTS, "fair": {self.TOTAL: 0.56}}))
        self.assertEqual(moved["cancels"], ["ord-1"])  # the line moved 1.7 cents since it was priced
        unknown = self.run_seed(self.ctx(open_orders=[self.bid(self.TOTAL)], memory={"starts": self.STARTS}))
        self.assertEqual(unknown["cancels"], ["ord-1"])  # no fair to hold its reading to
        other = self.ctx(market("KXNFLGAME-26SEP27TENNYG-NYG", 0.4, 0.5, "New York G wins"), open_orders=[self.bid(self.TOTAL)], memory=memory)
        self.assertEqual(self.run_seed(other)["cancels"], ["ord-1"])  # no market of its game is shown
        stale = self.ctx(open_orders=[self.bid(self.TOTAL)], memory=memory, fetched="2026-09-27T10:00:00.000Z")
        self.assertEqual(self.run_seed(stale)["cancels"], ["ord-1"])  # its game's lines are stale
        sell = {**self.bid(self.BUF), "side": "sell"}
        self.assertEqual(self.run_seed(self.ctx(open_orders=[sell], fetched="2026-09-27T10:00:00.000Z"))["cancels"], [])  # never a sell

    def test_at_most_twenty_cancels_the_starts_first_and_the_rest_remembered(self):
        orders = [self.bid(f"KXNFLGAME-26SEP27T{i:02d}X-T{i:02d}".replace("0", "Q").replace("1", "W").replace("2", "E"), oid=f"o{i}")
                  for i in range(22)]
        starts = {o["market"].rsplit("-", 1)[0]: ("2026-09-27T12:10:00Z" if i >= 17 else "2026-09-27T20:00:00Z") for i, o in enumerate(orders)}
        out = self.run_seed(self.ctx(open_orders=orders, memory={"starts": starts}))
        self.assertEqual(len(out["cancels"]), 20)
        self.assertEqual(out["cancels"][:5], ["o17", "o18", "o19", "o20", "o21"])  # inside the start buffer: first
        left = [o for o in orders if o["order_id"] not in out["cancels"]]
        self.assertEqual(len(left), 2)
        for order in left:  # a bid not cancelled this wake keeps its start, for the next
            self.assertIn(order["market"].rsplit("-", 1)[0], out["memory"]["starts"])

    def test_no_new_bid_once_forty_rest_and_the_memory_stays_small(self):
        now = "2026-09-26T12:00:00.000Z"
        board, odds, rows = synthetic(41, now)
        bids = [self.bid(row["market"], oid=f"o{i}", price=0.51) for i, row in enumerate(rows[:40])]
        ctx = ctx_for("ncaaf", now, markets=rows, open_orders=bids, cash=2000.0, equity=2000.0,
                      memory={"fair": {row["market"]: 0.6 for row in rows[:40]}})
        ctx["feeds"] = {"sports": {"ncaaf": {"t": now, "events": board}}, "odds": {"ncaaf": odds}}
        out = runner.decide(code_for("ncaaf"), ctx)
        self.assertTrue(out["ok"], out.get("error"))
        self.assertEqual((out["cancels"], out["intents"]), ([], []))  # the 41st game's edge waits for a free slot
        self.assertEqual(len(out["memory"]["fair"]), 40)
        self.assertLess(len(json.dumps(out["memory"])), 6000)
        ctx["open_orders"] = bids[:39]
        self.assertEqual([i["market"] for i in runner.decide(code_for("ncaaf"), ctx)["intents"]], [rows[39]["market"]])  # one slot

    def test_a_refused_taker_is_remembered_after_it_leaves_the_outcomes(self):
        refused = [{"at": self.NOW, "instrument": {"market_id": self.BUF}, "status": "refused",
                    "reason": "a real entry on sports-consensus-nfl must be a post-only limit until the family's pooled taker record is positive"}]
        first = self.run_seed(self.ctx(market(self.BUF, 0.55, 0.62, "Buffalo wins"), recent_order_outcomes=refused))
        self.assertEqual(first["memory"]["maker_only_until"], "2026-09-28T12:00:00Z")
        later = self.run_seed(self.ctx(market(self.BUF, 0.55, 0.62, "Buffalo wins"), memory={"maker_only_until": "2026-09-28T12:00:00Z"}))
        self.assertEqual([(i["limit_price"], i.get("post_only")) for i in later["intents"]], [(0.56, True)])
        lapsed = self.run_seed(self.ctx(market(self.BUF, 0.55, 0.62, "Buffalo wins"), memory={"maker_only_until": "2026-09-27T11:00:00Z"}))
        self.assertEqual([(i["limit_price"], i.get("post_only")) for i in lapsed["intents"]], [(0.62, None)])
        self.assertNotIn("maker_only_until", lapsed["memory"])

    def test_fee_multiplier_lowers_the_baseball_fee_and_no_other(self):
        rate = SEED["fee_rate"]
        self.assertEqual(rate("KXNFLGAME", 0.07, 0.5), 0.07)
        self.assertEqual(rate("KXNCAAFSPREAD", 0.07, 0.5), 0.07)
        self.assertEqual(rate("KXMLBTOTAL", 0.07, 0.5), 0.035)
        self.assertEqual(rate("KXMLBGAME", 0.07, 1.0), 0.07)
        self.assertEqual(rate("KXMLBGAME", 0.07, 0.0), 0.035)  # never under the series' own
        ctx = self.ctx(market(self.BUF, 0.55, 0.62, "Buffalo wins"))
        full = self.run_seed(ctx)
        ctx["params"]["fee_multiplier"] = 0.5
        self.assertEqual(self.run_seed(ctx)["intents"], full["intents"])  # the NFL pays the full rate either way

    def test_a_snapshot_without_its_rung_is_held_to_the_real_floor(self):
        ctx = self.ctx(market("KXNFLGAME-26SEP27LACBUF-LAC", 0.20, 0.30, "Los Angeles C wins"))
        del ctx["rung"]
        self.assertEqual([(i["leg"], i["limit_price"]) for i in self.run_seed(ctx)["intents"]], [("no", 0.71)])

    def test_a_taker_fits_free_cash_with_its_fee(self):
        out = self.run_seed(self.ctx(market(self.BUF, 0.55, 0.62, "Buffalo wins"), cash=5.1))
        (intent,) = out["intents"]
        cost = intent["quantity"] * 0.62 + SEED["fee"]("KXNFLGAME", intent["quantity"], 0.62, False, 0.07)
        self.assertLessEqual(cost, 5.1 * 0.98)
        self.assertEqual(intent["quantity"], 7)  # 8 would cost $5.09 with the fee: over the 2% headroom

    def test_a_line_whose_fetch_time_cannot_be_read_is_stale(self):
        for fetched in (None, "garbage", 17):
            ctx = self.ctx()
            ctx["feeds"]["odds"]["nfl"]["events"][0]["fetched"] = fetched  # the row's own t is fresh
            out = self.run_seed(ctx)
            self.assertEqual(out["intents"], [], fetched)
            self.assertIn("stale lines", out["thought"])

    def test_odd_shapes_never_crash_a_wake(self):
        odd = [None, float("nan"), float("inf"), -1, 0, "x", [], {}, [1], True, 1e308]
        base = self.ctx(open_orders=[self.bid(self.BUF, price=0.61)], positions=[{"market": "KXNFLGAME-26SEP27TENNYG-NYG", "quantity": 3}],
                        recent_order_outcomes=[{"status": "refused", "reason": "post-only"}], event_risk={"remaining_by_market_usd": {self.BUF: 5.0}},
                        memory={"starts": self.STARTS, "fair": {self.BUF: 0.73}, "maker_only_until": "2026-09-28T00:00:00Z"})
        paths = [("markets",), ("markets", 0), ("markets", 0, "yes_bid"), ("markets", 0, "title"), ("open_orders",), ("open_orders", 0),
                 ("open_orders", 0, "limit_price"), ("open_orders", 0, "quantity"), ("open_orders", 0, "leg"), ("positions",),
                 ("positions", 0, "quantity"), ("recent_order_outcomes",), ("recent_order_outcomes", 0), ("event_risk",),
                 ("event_risk", "remaining_by_market_usd"), ("limits",), ("limits", "max_order_usd"), ("fees",), ("fees", "kalshi_taker_rate"),
                 ("params", "sigma_margin"),  # (the runner itself merges ctx["params"] into PARAMS: a dict) ("memory",), ("memory", "starts"), ("memory", "fair"), ("memory", "maker_only_until"),
                 ("feeds",), ("feeds", "odds"), ("feeds", "odds", "nfl"), ("feeds", "odds", "nfl", "events"),
                 ("feeds", "odds", "nfl", "events", 0, "lines"), ("feeds", "odds", "nfl", "events", 0, "lines", 0, "implied_home"),
                 ("feeds", "sports", "nfl", "events"), ("feeds", "sports", "nfl", "events", 0, "home"), ("feeds", "sports", "nfl", "events", 0, "start"),
                 ("cash",), ("equity",), ("rung",), ("now",)]
        for path in paths:
            for value in odd:
                ctx = copy.deepcopy(base)
                where = ctx
                for key in path[:-1]:
                    where = where[key]
                where[path[-1]] = value
                with self.subTest(path=path, value=value):
                    out = runner.decide(code_for("nfl"), ctx)
                    self.assertTrue(out["ok"], out.get("error"))
                    for intent in out["intents"]:
                        self.assertEqual(intent["type"], "limit")
                        self.assertTrue(0.15 <= intent["limit_price"] < 1.0 and intent["quantity"] >= 1, intent)

    def test_a_college_saturday_wake_decides_fast_and_small(self):
        now = "2026-09-26T12:00:00.000Z"
        lines = {g["id"]: copy.deepcopy(SLATE["ncaaf"]["odds"]["401862779"]) for g in SLATE["ncaaf"]["board"]}
        rows = sorted((m for m in SLATE["ncaaf"]["markets"] if m["series"] in SERIES["ncaaf"]), key=lambda m: m["market"])[:500]
        out = runner.decide(code_for("ncaaf"), ctx_for("ncaaf", now, markets=rows, lines=lines))
        self.assertTrue(out["ok"], out.get("error"))  # the runner refuses a decision past its 5 seconds
        self.assertLess(out["seconds"], 5.0)
        self.assertIn("NCAAF: priced", out["thought"])
        self.assertLess(len(json.dumps(out["memory"])), 8192)

    def test_no_mutation_lowers_the_price_floor_or_takes_at_no_edge(self):
        described = runner.needs_of(code_for("nfl"))
        needs, params = described["needs"], described["params"]
        bounds = needs["parameter_rules"]["bounds"]
        self.assertGreaterEqual(bounds["min_price"][0], 0.15)  # the practice book's own floor
        self.assertGreater(bounds["min_edge_winner"][0], 0)
        self.assertGreater(bounds["min_edge_ladder"][0], 0)
        self.assertGreater(bounds["take_edge"][0], 0)
        for trial in range(200):
            child = parameters.mutate(params, seed=f"review:{trial}", needs=needs)
            self.assertGreaterEqual(child["min_price"], 0.15)
            self.assertGreaterEqual(child["take_edge"], max(child["min_edge_winner"], child["min_edge_ladder"]))
        self.assertEqual(SEED["LONGSHOT_FLOOR_REAL"], 0.30)  # a constant: no knob reaches it


class Founders(unittest.TestCase):
    LEAGUES = ("nfl", "ncaaf", "mlb", "mls", "ligamx")

    def test_a_row_per_league_at_the_end_of_seeds_each_its_own_family(self):
        rows = [row for row in seeds.SEEDS if row["file"] == "sports_consensus.py"]
        self.assertEqual([row["name"] for row in rows], [f"consensus-{league}" for league in self.LEAGUES])
        self.assertEqual([row["family"] for row in rows], [f"sports-consensus-{league}" for league in self.LEAGUES])
        for row in rows:
            self.assertIn("Unmeasured", row["why"])

    def test_each_founder_is_seated_on_the_sports_desk_with_its_league(self):
        desk = niches.load()["kalshi-sports"]
        self.assertEqual(desk.max_members, 25)  # 19, the five founders here, and the UFC founder (test_sports_h2h.py)
        for league in self.LEAGUES:
            with self.subTest(league):
                row = founder(league)
                self.assertEqual((row["key"], row["seed"], row["seat_full_league"]), (f"consensus-{league}", f"consensus-{league}", True))
                # Four seats can be freed before the forward-first run's F3: college football first, then MLB, then the NFL.
                self.assertEqual(row["seat_priority"], {"ncaaf": 10, "mlb": 20, "nfl": 30, "mls": 60, "ligamx": 70}[league])
                code = code_for(league)
                check_code(code)
                described = runner.needs_of(code)
                self.assertTrue(described["ok"], described)
                needs, params = described["needs"], described["params"]
                self.assertEqual((needs["venue"], needs["horizon"], needs["style"]), ("kalshi", "day", "model-versus-market"))
                self.assertEqual(needs["series"], SERIES[league])
                self.assertEqual(needs["feeds"], {"odds": [league], "sports": [league]})
                self.assertLessEqual(needs["max_hours_to_close"], 48)  # the day horizon's rule
                self.assertEqual(needs["wake_minutes"], 10)
                report = parameters.inspect(params, needs)
                self.assertTrue(report["valid"], report["errors"])
                self.assertEqual(report["frozen"], [])  # every knob is bounded, so a mutation may move any
                for trial in range(20):
                    child = parameters.mutate(params, seed=f"{league}:{trial}", needs=needs)
                    self.assertTrue(parameters.inspect(child, needs)["valid"])

    def test_every_founder_decides_on_its_leagues_slate(self):
        # A wake is shown at most 200 markets (`KalshiData.markets`): the recorded game's first, then the slate's.
        # The runner refuses a decision past its 5 seconds (`ok` False). Measured unloaded: 0.26 s for the whole
        # 4,476-market college Saturday at once, 0.02 s for 200.
        for league, (game, code, now) in GAMES.items():
            with self.subTest(league):
                rows = sorted((m for m in SLATE[league]["markets"] if m["series"] in SERIES[league]),
                              key=lambda m: m["market"].split("-")[1] != code)
                out = runner.decide(code_for(league), ctx_for(league, now, markets=rows[:200]))
                self.assertTrue(out["ok"], out.get("error"))
                self.assertIn(f"{league.upper()}: priced", out["thought"])
                self.assertNotIn("priced 0 of", out["thought"])
                self.assertLessEqual(out["thought"].count(". "), 2)


if __name__ == "__main__":
    unittest.main()
