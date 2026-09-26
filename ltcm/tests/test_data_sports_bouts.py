"""ESPN's individual-sport shapes (K1c of the Kalshi-scale run, Sept 25, 2026): a UFC card is a board
row a BOUT, and the core API prices each bout's two athletes. Recorded live that morning:
fixtures/feeds/espn_scoreboard_ufc_20260926.json (the default mma/ufc board, the Sept 26 Fight Night,
trimmed to the fields read) and espn_core_odds_ufc_401911630.json (DraftKings' line on its main event,
Rosas Jr. vs Barcelos)."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ltcm.data import DataError
from ltcm.data.sports import CORE_HOST, HOST, Sports, event_row, event_rows, parse_core_odds
from ltcm.tests.fakes import FakeTransport
from ltcm.tests.test_data_sports import FINAL_EVENT, PRE_EVENT

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"
UFC = HOST + "/apis/site/v2/sports/mma/ufc/scoreboard"
CARD = json.loads((FIXTURES / "espn_scoreboard_ufc_20260926.json").read_text(encoding="utf-8"))
MAIN_EVENT = json.loads((FIXTURES / "espn_core_odds_ufc_401911630.json").read_text(encoding="utf-8"))


class Cards(unittest.TestCase):
    def test_a_card_is_a_row_a_bout_with_its_own_start_and_its_cards_id(self):
        board = Sports(FakeTransport({UFC: CARD})).board("mma/ufc")
        self.assertEqual(board["day"], "2026-09-26")
        rows = board["events"]
        self.assertEqual(len(rows), 12)  # one card, twelve bouts
        self.assertEqual({(r["card_id"], r["card"]) for r in rows}, {("600061266", "UFC Fight Night: Rosas Jr. vs. Barcelos")})
        self.assertEqual(len({r["id"] for r in rows}), 12)
        # The prelims start at 21:00Z and the main card at 00:00Z: each bout carries its segment's start.
        self.assertEqual(sorted({r["start"] for r in rows}), ["2026-09-26T21:00:00Z", "2026-09-27T00:00:00Z"])
        self.assertEqual({r["status"] for r in rows}, {"pre"})
        first = rows[0]
        self.assertEqual((first["id"], first["name"], first["short_name"]), ("401914472", "Vanessa Demopoulos vs Yazmin Jauregui", "W Strawweight"))
        self.assertEqual(first["home"], {"team": "Vanessa Demopoulos", "short": "V. Demopoulos", "abbrev": None, "location": None,
                                         "nickname": None, "id": "4683395", "score": None, "winner": False, "record": "11-8-0"})
        # No homeAway on an MMA competitor: order 1 is home, whichever way ESPN lists the two.
        main = next(r for r in rows if r["id"] == "401911630")
        self.assertEqual((main["home"]["team"], main["away"]["team"]), ("Raul Rosas Jr.", "Raoni Barcelos"))
        self.assertEqual((main["home"]["id"], main["away"]["id"]), ("5088844", "3075570"))

    def test_a_bout_that_is_not_two_athletes_one_of_each_order_is_left_out(self):
        card = copy.deepcopy(CARD["events"][0])
        bouts = card["competitions"]
        bouts[0]["competitors"] = bouts[0]["competitors"][:1]  # one athlete
        bouts[1]["competitors"][1]["order"] = bouts[1]["competitors"][0]["order"]  # two of one order
        bouts[2]["competitors"][0].pop("athlete")  # a side that is not an athlete
        self.assertEqual([r["id"] for r in event_rows(card)], [b["id"] for b in bouts[3:]])

    def test_a_game_of_two_teams_is_its_one_row_as_before(self):
        self.assertEqual(event_rows(PRE_EVENT), [event_row(PRE_EVENT)])
        self.assertEqual(event_rows(FINAL_EVENT), [event_row(FINAL_EVENT)])
        self.assertEqual(event_rows({"id": "junk"}), [])
        self.assertNotIn("card_id", event_rows(PRE_EVENT)[0])


class BoutOdds(unittest.TestCase):
    def test_each_athletes_price_is_read_with_the_athletes_espn_id(self):
        line = parse_core_odds(MAIN_EVENT)[0]
        self.assertEqual((line["provider"], line["details"], line["home_ml"], line["away_ml"]), ("DraftKings", "R. Rosas Jr. -155", -155, 130))
        self.assertEqual((line["implied_home"], line["implied_away"], line["draw_ml"], line["implied_draw"]), (0.583, 0.417, None, None))
        self.assertEqual((line["home_athlete"], line["away_athlete"]), ("5088844", "3075570"))  # Rosas Jr. home, as on the board
        self.assertEqual(line["open"]["home_ml"], -205)
        # A team game's row is unchanged: no athlete keys.
        team = parse_core_odds(json.loads((FIXTURES / "espn_core_odds_401872948.json").read_text(encoding="utf-8")))[0]
        self.assertNotIn("home_athlete", team)

    def test_a_bouts_odds_are_asked_by_its_cards_id_and_its_own(self):
        url = CORE_HOST + "/v2/sports/mma/leagues/ufc/events/600061266/competitions/401911630/odds"
        transport = FakeTransport({url: MAIN_EVENT, CORE_HOST + "/v2/sports/mma/*": (404, {}, b'{"error": "No event found"}')})
        client = Sports(transport)
        self.assertEqual(client.core_odds("mma/ufc", "401911630", card="600061266")[0]["home_athlete"], "5088844")
        self.assertEqual(transport.calls[-1]["url"], url)
        # The bout's id alone answers 404 at ESPN, which reads as no line: the card's id is what finds it.
        self.assertEqual(client.core_odds("mma/ufc", "401911630"), [])
        with self.assertRaises(DataError):
            client.core_odds("mma/ufc", "401911630", card="../600061266")


if __name__ == "__main__":
    unittest.main()
