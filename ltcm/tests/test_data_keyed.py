"""The keyed sources the owner switches on (Sept 24, 2026): EIA's prices and The Odds API's lines.

UNVERIFIED against a live answer: no key existed on Sept 24, 2026, so the payloads below follow
each API's documentation (https://www.eia.gov/opendata/documentation.php,
https://the-odds-api.com/liveapi/guides/v4/) rather than a recording.
"""

from __future__ import annotations

import unittest

from ltcm.data import DataError
from ltcm.data.eia import HOST as EIA_HOST, Eia, parse_series
from ltcm.data.oddsapi import HOST as ODDS_HOST, OddsApi, parse_odds
from ltcm.tests.fakes import FakeTransport

WTI = {"response": {"total": 3, "dateFormat": "YYYY-MM-DD", "frequency": "daily", "data": [
    {"period": "2026-09-21", "duoarea": "YCUOK", "area-name": "NA", "product": "EPCWTI", "product-name": "WTI Crude Oil",
     "process": "PF4", "process-name": "Spot Price FOB", "series": "RWTC", "series-description": "Cushing, OK WTI Spot Price FOB (Dollars per Barrel)",
     "value": 70.12, "units": "$/BBL"},
    {"period": "2026-09-22", "duoarea": "YCUOK", "series": "RWTC", "value": "71.05", "units": "$/BBL"},
    {"period": "2026-09-19", "duoarea": "YCUOK", "series": "RWTC", "value": None, "units": "$/BBL"}]}}

GAMES = [{"id": "e912", "sport_key": "americanfootball_nfl", "commence_time": "2026-09-25T00:15:00Z",
          "home_team": "Green Bay Packers", "away_team": "Atlanta Falcons", "bookmakers": [
              {"key": "draftkings", "title": "DraftKings", "last_update": "2026-09-24T03:10:00Z", "markets": [
                  {"key": "h2h", "last_update": "2026-09-24T03:10:00Z",
                   "outcomes": [{"name": "Green Bay Packers", "price": -245}, {"name": "Atlanta Falcons", "price": 200}]}]},
              {"key": "fanduel", "title": "FanDuel", "last_update": "2026-09-24T03:12:00Z", "markets": [
                  {"key": "h2h", "last_update": "2026-09-24T03:12:00Z",
                   "outcomes": [{"name": "Green Bay Packers", "price": -230}, {"name": "Atlanta Falcons", "price": 190}]}]}]},
         {"id": "e913", "commence_time": "2026-09-28T17:00:00Z", "home_team": "A", "away_team": "B", "bookmakers": []}]


class EiaSeries(unittest.TestCase):
    def test_the_newest_value_and_the_recent_ones(self):
        row = parse_series("WTI", WTI)
        self.assertEqual((row["series"], row["period"], row["value"], row["units"]), ("RWTC", "2026-09-22", 71.05, "$/BBL"))
        self.assertEqual(row["recent"], [{"period": "2026-09-22", "value": 71.05}, {"period": "2026-09-21", "value": 70.12}])
        with self.assertRaises(DataError):
            parse_series("WTI", {"error": "API_KEY_INVALID"})
        with self.assertRaises(DataError):
            parse_series("BRENT", WTI)  # an answer about another series is not Brent's

    def test_asked_with_the_key_in_the_query_and_never_without_one(self):
        transport = FakeTransport({EIA_HOST + "/v2/petroleum/pri/spt/data/?*": WTI})
        self.assertEqual(Eia("k" * 40, transport).series("wti")["value"], 71.05)
        query = transport.calls[-1]["query"]
        self.assertEqual((query["api_key"], query["facets[series][]"], query["frequency"]), ("k" * 40, "RWTC", "daily"))
        with self.assertRaises(DataError):
            Eia("", transport)


class TheOddsApi(unittest.TestCase):
    def test_the_consensus_is_the_mean_of_the_books_devigged_probabilities(self):
        rows = parse_odds(GAMES)
        game = rows[0]
        dk = (245 / 345) / (245 / 345 + 100 / 300)
        fd = (230 / 330) / (230 / 330 + 100 / 290)
        self.assertEqual((game["books"], game["consensus"]["home"], game["last_update"]), (2, round((dk + fd) / 2, 4), "2026-09-24T03:12:00Z"))
        self.assertAlmostEqual(game["consensus"]["home"] + game["consensus"]["away"], 1.0, places=3)
        self.assertEqual((rows[1]["books"], rows[1]["consensus"]), (0, None))  # no book prices it: None, never 50/50
        with self.assertRaises(DataError):
            parse_odds({"message": "Invalid api key"})

    def test_asked_per_sport_with_the_key(self):
        transport = FakeTransport({ODDS_HOST + "/v4/sports/americanfootball_nfl/odds?*": GAMES})
        self.assertEqual(len(OddsApi("q" * 32, transport).odds("nfl")), 2)
        self.assertEqual(transport.calls[-1]["query"]["apiKey"], "q" * 32)
        with self.assertRaises(DataError):
            OddsApi("q" * 32, transport).odds("cricket")


if __name__ == "__main__":
    unittest.main()
