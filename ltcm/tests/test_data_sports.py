"""ESPN: league scoreboards as flat rows, one game's summary, matching a Kalshi title to a game."""

from __future__ import annotations

import unittest

from ltcm.data import DataError
from ltcm.data.sports import HOST, LEAGUES, USER_AGENT, Sports, event_row
from ltcm.tests.fakes import Clock, FakeTransport

NFL = HOST + "/apis/site/v2/sports/football/nfl/scoreboard"
EPL = HOST + "/apis/site/v2/sports/soccer/eng.1/scoreboard"
SUMMARY = HOST + "/apis/site/v2/sports/football/nfl/summary?event="


def team(team_id, location, nickname, abbrev):
    return {"id": team_id, "location": location, "name": nickname, "abbreviation": abbrev,
            "displayName": f"{location} {nickname}", "shortDisplayName": nickname}


def competitor(side, team_row, score, winner=None, record="1-1", key="records"):
    return {"homeAway": side, "score": score, "winner": winner, "team": team_row,
            key: [{"type": "total", "summary": record}, {"type": "home", "summary": "1-0"}]}


BILLS, LIONS = team("2", "Buffalo", "Bills", "BUF"), team("8", "Detroit", "Lions", "DET")
FALCONS, PANTHERS = team("1", "Atlanta", "Falcons", "ATL"), team("29", "Carolina", "Panthers", "CAR")

FINAL_EVENT = {
    "id": "401872932", "name": "Detroit Lions at Buffalo Bills", "shortName": "DET @ BUF", "date": "2026-09-18T00:15Z",
    "competitions": [{
        "id": "401872932", "date": "2026-09-18T00:15Z",
        "competitors": [competitor("home", BILLS, "41", True, "2-0"), competitor("away", LIONS, "31", False, "1-1")],
        "status": {"clock": 0.0, "displayClock": "0:00", "period": 4,
                   "type": {"id": "3", "name": "STATUS_FINAL", "state": "post", "completed": True, "description": "Final", "detail": "Final", "shortDetail": "Final"}},
        "odds": None,
    }],
}
PRE_ODDS = {
    "provider": {"id": "100", "name": "Draft Kings"}, "details": "CAR -2.5", "overUnder": 43.5, "spread": 2.5,
    "awayTeamOdds": {"favorite": True, "underdog": False, "team": {"abbreviation": "CAR"}},
    "homeTeamOdds": {"favorite": False, "underdog": True, "team": {"abbreviation": "ATL"}},
    "moneyline": {"home": {"close": {"odds": "+130"}, "open": {"odds": "-120"}}, "away": {"close": {"odds": "-155"}, "open": {"odds": "+100"}}},
}
PRE_EVENT = {
    "id": "401872933", "name": "Carolina Panthers at Atlanta Falcons", "shortName": "CAR @ ATL", "date": "2026-09-20T17:00Z",
    "competitions": [{
        "id": "401872933",
        "competitors": [competitor("home", FALCONS, "0", None, "0-1"), competitor("away", PANTHERS, "0", None, "1-1")],
        "status": {"clock": 0.0, "displayClock": "0:00", "period": 0,
                   "type": {"id": "1", "name": "STATUS_SCHEDULED", "state": "pre", "completed": False, "detail": "Sun, September 20th at 1:00 PM EDT", "shortDetail": "9/20 - 1:00 PM EDT"}},
        "odds": [PRE_ODDS],
    }],
}
SCOREBOARD_JSON = {"events": [FINAL_EVENT, PRE_EVENT, {"id": "junk"}], "leagues": [], "season": {}}

EPL_JSON = {"events": [{
    "id": "740001", "name": "Chelsea at Arsenal", "shortName": "CHE @ ARS", "date": "2026-09-19T16:30Z",
    "competitions": [{
        "competitors": [competitor("home", team("359", "Arsenal", "Arsenal", "ARS"), "1"), competitor("away", team("363", "Chelsea", "Chelsea", "CHE"), "1")],
        "status": {"displayClock": "67'", "period": 2, "type": {"state": "in", "completed": False, "shortDetail": "67'"}},
        "odds": [{"provider": {"name": "Draft Kings"}, "details": "CHE +145", "overUnder": 3.5, "spread": None, "homeTeamOdds": None, "awayTeamOdds": None}],
    }],
}]}

FINAL_SUMMARY = {
    "header": {"id": "401872932", "competitions": [{
        "id": "401872932", "date": "2026-09-18T00:15Z",
        "competitors": [competitor("home", BILLS, "41", True, "2-0", key="record"), competitor("away", LIONS, "31", False, "1-1", key="record")],
        "status": {"displayClock": "0:00", "period": 4, "type": {"state": "post", "completed": True, "shortDetail": "Final"}},
    }]},
    "winprobability": [{"homeWinPercentage": 0.55, "tiePercentage": 0.0, "playId": "1"}, {"homeWinPercentage": 0.93, "tiePercentage": 0.02, "playId": "2"}],
    "pickcenter": [{"provider": {"name": "Draft Kings"}, "details": "BUF -5.5", "overUnder": 54.5, "spread": 5.5,
                    "homeTeamOdds": {"favorite": True, "moneyLine": -245}, "awayTeamOdds": {"favorite": False, "moneyLine": 200}}],
    "predictor": {"homeTeam": {"id": "2", "gameProjection": "71.3"}, "awayTeam": {"id": "8", "gameProjection": "28.4"}},
    "drives": {"previous": [
        {"plays": [{"text": "Josh Allen pass complete", "period": {"number": 4}}]},
        {"plays": [{"text": "Kneel down", "period": {"number": 4}}, {"text": None}, {"text": "END GAME", "period": {"number": 4}}]},
    ]},
}
PLAYS_SUMMARY = {
    "header": {"id": "5", "competitions": [{
        "competitors": [competitor("home", team("23", "Pittsburgh", "Pirates", "PIT"), "7"), competitor("away", team("158", "Milwaukee", "Brewers", "MIL"), "4")],
        "status": {"period": 9, "type": {"state": "in", "completed": False}},
    }]},
    "plays": [{"text": "Ortiz grounded out to first."}, {"text": None, "type": {"text": "End Batter/Pitcher"}}],
    "winprobability": [],
}


class SportsCase(unittest.TestCase):
    def transport(self, **overrides):
        routes = {NFL: SCOREBOARD_JSON, EPL: EPL_JSON, SUMMARY + "401872932": FINAL_SUMMARY,
                  HOST + "/apis/site/v2/sports/baseball/mlb/summary?event=5": PLAYS_SUMMARY}
        routes.update(overrides)
        return FakeTransport(routes)

    def sports(self, transport=None):
        return Sports(transport or self.transport(), clock=Clock("2026-09-18T06:30:00Z"))


class ScoreboardTests(SportsCase):
    def test_rows_carry_status_score_records_and_the_home_signed_line(self):
        transport = self.transport()
        rows = self.sports(transport).scoreboard("nfl")
        self.assertEqual(len(rows), 2, "an event without competitions is dropped, not raised")
        final, pre = rows
        self.assertEqual(final["id"], "401872932")
        self.assertEqual(final["name"], "Detroit Lions at Buffalo Bills")
        self.assertEqual(final["short_name"], "DET @ BUF")
        self.assertEqual(final["start"], "2026-09-18T00:15:00Z")
        self.assertEqual((final["status"], final["completed"], final["period"], final["clock"], final["detail"]), ("post", True, 4, "0:00", "Final"))
        self.assertEqual(final["home"], {"team": "Buffalo Bills", "short": "Bills", "abbrev": "BUF", "location": "Buffalo", "nickname": "Bills", "id": "2",
                                         "score": 41, "winner": True, "record": "2-0"})
        self.assertEqual(final["away"]["score"], 31)
        self.assertIsNone(final["odds"])
        self.assertEqual(pre["status"], "pre")
        self.assertEqual(pre["odds"], {"details": "CAR -2.5", "spread": 2.5, "over_under": 43.5, "home_ml": 130, "away_ml": -155, "provider": "Draft Kings"})
        self.assertEqual(transport.last["url"], NFL)
        self.assertEqual(transport.last["headers"]["User-Agent"], USER_AGENT)
        self.assertEqual(USER_AGENT, "curl/8.0")

    def test_soccer_odds_keep_details_and_total_without_a_spread(self):
        rows = self.sports().scoreboard("epl")
        self.assertEqual(rows[0]["status"], "in")
        self.assertEqual(rows[0]["clock"], "67'")
        self.assertEqual(rows[0]["odds"], {"details": "CHE +145", "spread": None, "over_under": 3.5, "home_ml": None, "away_ml": None, "provider": "Draft Kings"})

    def test_every_league_has_a_path_and_failures_are_data_errors(self):
        self.assertEqual(set(LEAGUES), {"nfl", "nba", "mlb", "nhl", "ncaaf", "ncaab", "mls", "epl"})
        with self.assertRaises(DataError):
            self.sports().scoreboard("xfl")
        with self.assertRaises(DataError):
            self.sports(self.transport(**{NFL: (403, {}, b"forbidden")})).scoreboard("nfl")
        with self.assertRaises(DataError):
            self.sports(self.transport(**{NFL: {"leagues": []}})).scoreboard("nfl")
        self.assertIsNone(event_row({"id": "1", "competitions": []}))


class GameTests(SportsCase):
    def test_a_summary_adds_last_play_win_probability_predictor_and_pickcenter_odds(self):
        transport = self.transport()
        game = self.sports(transport).game("nfl", 401872932)
        self.assertEqual(transport.last["url"], SUMMARY + "401872932")
        self.assertEqual(game["name"], "Detroit Lions at Buffalo Bills", "built from the teams when the header has no name")
        self.assertEqual((game["status"], game["home"]["score"], game["home"]["record"]), ("post", 41, "2-0"))
        self.assertEqual(game["last_play"], "END GAME")
        self.assertEqual(game["win_probability"], {"home": 0.93, "away": 0.05, "tie": 0.02})
        self.assertEqual(game["predictor"], {"home": 71.3, "away": 28.4})
        self.assertEqual(game["odds"], {"details": "BUF -5.5", "spread": -5.5, "over_under": 54.5, "home_ml": -245, "away_ml": 200, "provider": "Draft Kings"})
        self.assertEqual(game["as_of"], "2026-09-18T06:30:00Z")

    def test_other_sports_use_a_flat_plays_list_and_missing_blocks_are_none(self):
        game = self.sports().game("mlb", "5")
        self.assertEqual(game["last_play"], "Ortiz grounded out to first.")
        self.assertIsNone(game["win_probability"])
        self.assertIsNone(game["predictor"])
        self.assertIsNone(game["odds"])
        with self.assertRaises(DataError):
            self.sports(self.transport(**{SUMMARY + "401872932": {"boxscore": {}}})).game("nfl", "401872932")
        with self.assertRaises(DataError):
            self.sports().game("nfl", "")


class MatchTests(SportsCase):
    def test_the_first_named_team_sets_the_side(self):
        rows = self.sports().scoreboard("nfl")
        found = Sports.match_kalshi("Will the Falcons beat the Panthers?", rows)
        self.assertEqual((found["id"], found["side"], found["side_team"], found["matched_teams"]), ("401872933", "home", "Atlanta Falcons", 2))
        found = Sports.match_kalshi("Will Carolina win against Atlanta on Sunday?", rows)
        self.assertEqual((found["id"], found["side"]), ("401872933", "away"))
        found = Sports.match_kalshi("DET to win at BUF", rows)
        self.assertEqual((found["id"], found["side"]), ("401872932", "away"))
        found = Sports.match_kalshi("Will the Buffalo Bills win?", rows)
        self.assertEqual((found["id"], found["side"]), ("401872932", "home"))
        self.assertIsNone(Sports.match_kalshi("Will the Yankees beat the Red Sox?", rows))
        self.assertIsNone(Sports.match_kalshi("", rows))
        self.assertIsNone(Sports.match_kalshi("Bills", []))
        self.assertNotIn("side", rows[0], "the scoreboard rows themselves are not mutated")


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------- ESPN's core API, Sept 24, 2026
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from ltcm.data.sports import CORE_HOST, implied, implied_home, parse_core_odds, parse_predictor  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"
CORE_ODDS = CORE_HOST + "/v2/sports/football/leagues/nfl/events/401872948/competitions/401872948/odds"
CORE_PREDICTOR = CORE_HOST + "/v2/sports/football/leagues/nfl/events/401872948/competitions/401872948/predictor"


def core(name):
    """ESPN core API answers for Falcons at Packers, recorded Sept 24, 2026 at 03:22Z (odds without their bet links)."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CoreApi(unittest.TestCase):
    def test_the_recorded_lines_and_predictor(self):
        lines = parse_core_odds(core("espn_core_odds_401872948.json"))
        self.assertEqual(lines, [{"provider": "Draft Kings", "priority": 1, "details": "GB -5.5", "spread": -5.5, "over_under": 42.5,
                                  "home_ml": -245, "away_ml": 200, "draw_ml": None, "implied_home": 0.6806, "implied_away": 0.3194,
                                  "implied_draw": None, "over_odds": -118, "under_odds": -102, "implied_over": 0.5174,
                                  "home_spread_odds": -105, "away_spread_odds": -115, "implied_home_cover": 0.4892,
                                  "open": {"spread": -7.5, "home_ml": -360, "away_ml": 285}}])
        self.assertEqual(parse_predictor(core("espn_core_predictor_401872948.json")),
                         {"home": 0.74465, "away": 0.25332, "tie": 0.00203, "modified": "2026-09-23T23:27Z"})
        self.assertIsNone(parse_predictor({"homeTeam": {"statistics": []}}))
        self.assertEqual((implied_home(-110, -110), implied_home(None, 120)), (0.5, None))

    def test_the_core_api_is_asked_per_competition_and_a_game_without_a_line_has_none(self):
        transport = FakeTransport({CORE_ODDS: core("espn_core_odds_401872948.json"), CORE_PREDICTOR: core("espn_core_predictor_401872948.json"),
                                   CORE_HOST + "/v2/sports/soccer/*": (404, {}, b'{"error": "not found"}')})
        client = Sports(transport)
        self.assertEqual(client.core_odds("nfl", "401872948")[0]["provider"], "Draft Kings")
        self.assertEqual(client.core_predictor("nfl", "401872948")["home"], 0.74465)
        self.assertEqual(client.core_odds("soccer/eng.1", "704512"), [])
        self.assertIsNone(client.core_predictor("soccer/eng.1", "704512"))
        self.assertEqual(transport.calls[0]["headers"]["User-Agent"], USER_AGENT)
        with self.assertRaises(DataError):
            client.core_odds("nfl", "../401872948")

    def test_a_draw_price_makes_the_three_way_de_vig_and_a_run_line_its_own_price(self):
        # Recorded Sept 25, 2026 ~06:30Z: NYC at Atlanta United (MLS) and Baltimore at the Yankees (MLB).
        soccer = parse_core_odds(core("espn_core_odds_761830.json"))[0]
        self.assertEqual((soccer["home_ml"], soccer["away_ml"], soccer["draw_ml"]), (120, 190, 250))
        self.assertEqual((soccer["implied_home"], soccer["implied_away"], soccer["implied_draw"]), (0.4189, 0.3178, 0.2633))
        self.assertAlmostEqual(soccer["implied_home"] + soccer["implied_away"] + soccer["implied_draw"], 1.0, places=3)
        self.assertEqual((soccer["over_under"], soccer["implied_over"]), (2.5, 0.5506))
        baseball = parse_core_odds(core("espn_core_odds_401817088.json"))[0]
        # The run line's prices are under `current.spread`, not `spreadOdds`: home -1.5 at +169, away +1.5 at -206.
        self.assertEqual((baseball["spread"], baseball["home_spread_odds"], baseball["away_spread_odds"]), (-1.5, 169, -206))
        self.assertEqual((baseball["implied_home_cover"], baseball["implied_home"], baseball["draw_ml"], baseball["implied_draw"]),
                         (0.3558, 0.5631, None, None))
        self.assertEqual(implied(120, 190, 250), [0.4189, 0.3178, 0.2633])
        self.assertIsNone(implied(120, None, 250))


class Boards(unittest.TestCase):
    def test_a_board_reads_its_query_and_says_which_day_a_daily_board_shows(self):
        mlb = HOST + "/apis/site/v2/sports/baseball/mlb/scoreboard"
        stale = json.loads((FIXTURES / "espn_scoreboard_mlb_default_20260924.json").read_text(encoding="utf-8"))
        today = json.loads((FIXTURES / "espn_scoreboard_mlb_20260925.json").read_text(encoding="utf-8"))
        transport = FakeTransport({mlb: lambda method, url, body: today if "dates=20260925" in url else stale})
        client = Sports(transport)
        # At 06:18Z Sept 25 the default MLB board was still Sept 24's, every game final.
        board = client.board("mlb")
        self.assertEqual((board["day"], {e["status"] for e in board["events"]}), ("2026-09-24", {"post"}))
        dated = client.board("mlb", "dates=20260925")
        # A dated board does not say its day (the live answer carries no `day`): the query does.
        self.assertEqual((dated["day"], [e["short_name"] for e in dated["events"]][:2]), (None, ["CHC @ BOS", "BAL @ NYY"]))
        self.assertEqual(transport.calls[-1]["url"], mlb + "?dates=20260925")
        self.assertEqual(client.scoreboard("mlb"), board["events"])
