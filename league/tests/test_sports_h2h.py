"""The UFC founder (K1c of the Kalshi-scale run, Sept 25, 2026): Kalshi's fight markets priced from the
sportsbook moneyline the `odds` feed records, each fight found by its fighters' names.

Recorded live at 10:45-10:56Z that day (fixtures/sports_h2h_ufc_20260926.json): ESPN's default mma/ufc
board (the Sept 26 Fight Night, twelve bouts), the core API's odds of every bout on it (DraftKings on
ten, none on two), and every open KXUFCFIGHT market (the Sept 26 card, the Sept 29 Contender Series and
UFC 332 on Oct 3). The board and the odds go through the House's own parsers (`event_rows`,
`parse_core_odds`), so these tests read what the recorder would store.
"""

from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from league import feeds, niches, parameters, runner, seeds
from league.feeds import request_feed, requested
from league.safety import check_code
from league.tests.test_feed_recorders import RecorderCase, epoch
from league.tests.test_seeds import SeedCase
from ltcm.data.sports import CORE_HOST, HOST, event_rows, parse_core_odds
from ltcm.tests.fakes import FakeTransport

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sports_h2h_ufc_20260926.json"
RECORDED = json.loads(FIXTURE.read_text(encoding="utf-8"))
BOARD = [row for event in RECORDED["board"]["events"] for row in event_rows(event)]
LINES = {bout: parse_core_odds(raw) for bout, raw in RECORDED["odds"].items()}
NOW = "2026-09-25T13:00:00.000Z"
UFC = HOST + "/apis/site/v2/sports/mma/ufc/scoreboard"
CARD_FIGHTS = ("DEMJAU", "DUMPER", "HERDUM", "CASHEI", "JACSIM", "BELEDW", "HARBRE", "OSMUUL", "HIENAK", "VIEBRY", "ROSBAR")


def module() -> dict:
    namespace: dict = {"__name__": "strategy"}
    exec(compile(seeds.load("h2h-ufc"), "strategy.py", "exec"), namespace)  # noqa: S102 - the seed passed check_code
    return namespace


SEED = module()


def founder() -> dict:
    return next(f for f in niches.load()["kalshi-sports"].founders if f["key"] == "h2h-ufc")


def code() -> str:
    return niches.founder_code(seeds.load("h2h-ufc"), niches.load()["kalshi-sports"], founder())


def at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def shown(now: str = NOW) -> list:
    """The KXUFCFIGHT markets a wake at `now` is shown (the founder's window: 0.5 to 42 hours to the expected end)."""
    out = []
    for row in RECORDED["markets"]:
        hours = (at(row["expected_end"]) - at(now)).total_seconds() / 3600.0
        if 0.5 <= hours <= 42:
            out.append({**{k: v for k, v in row.items() if k != "expected_end"}, "hours_to_close": round(hours, 4)})
    return out


def odds_row(fetched: str, lines: dict | None = None, board: list | None = None) -> dict:
    """The `odds` feed's ufc row, as `SportsOdds.poll` writes it."""
    lines = LINES if lines is None else lines
    return {"t": fetched, "league": "ufc", "events": [
        {"id": bout["id"], "name": bout["name"], "start": bout["start"], "home": bout["home"]["team"], "away": bout["away"]["team"],
         "fetched": fetched, "lines": copy.deepcopy(lines.get(bout["id"]) or []), "win_probability": None}
        for bout in (board or BOARD)]}


def ctx_for(now: str = NOW, *, markets=None, lines=None, fetched=None, board=None, **over) -> dict:
    ctx = {"now": now, "venue": "kalshi", "rung": 1, "params": dict(founder().get("params") or {}), "memory": {},
           "cash": 200.0, "equity": 200.0, "limits": {"max_position_usd": 20.0, "max_order_usd": 20.0},
           "fees": {"crypto_taker": 0.0025, "crypto_maker": 0.0015, "kalshi_taker_rate": 0.07}, "positions": [], "open_orders": [],
           "recent_order_outcomes": [], "markets": copy.deepcopy(markets if markets is not None else shown(now)),
           "feeds": {"sports": {"ufc": {"t": now, "league": "ufc", "espn": "mma/ufc", "events": copy.deepcopy(board or BOARD)}},
                     "odds": {"ufc": odds_row(fetched or now, lines, board)}}}
    ctx.update(over)
    return ctx


def parse(ticker: str, title: str):
    return SEED["parse_h2h"]({"market": ticker, "title": title})


# ---------------------------------------------------------------------------------- the recorder
class Recorder(RecorderCase):
    """The `sports` board and the `odds` rows cover UFC: a row a bout, each bout's line asked by its card."""

    def transport(self) -> FakeTransport:
        dated = {k: v for k, v in RECORDED["board"].items() if k != "day"}

        def board(method, url, body):
            query = url.partition("?")[2]
            return RECORDED["board"] if not query else dated if query == "dates=20260926" else {"events": []}

        def odds(method, url, body):
            card, bout = url.split("/events/")[1].split("/competitions/")[0], url.split("/competitions/")[1].split("/")[0]
            if card != "600061266" or bout not in RECORDED["odds"]:
                return 404, {}, b'{"error": {"message": "No event found", "code": 404}}'
            return RECORDED["odds"][bout]

        return FakeTransport({UFC: board, CORE_HOST + "/v2/sports/mma/leagues/ufc/events/*": odds})

    def test_the_card_is_recorded_a_row_a_bout_and_every_bouts_line_by_its_card(self):
        self.clock.set(epoch(NOW))
        fake = self.transport()
        store = self.recorder({"sports": ["ufc"], "odds": ["ufc"]}, transports=fake)
        out = store.run()
        self.assertEqual(out["failed"], [])
        # The default board shows Sept 26; today's dated board is asked beside it (empty: no card today), never a past day.
        boards = [call["url"] for call in fake.calls if call["url"].startswith(UFC)]
        self.assertEqual(boards, [UFC, UFC + "?dates=20260925"])
        row = store.latest({"sports": ["ufc"]}, self.clock())["sports"]["ufc"]
        self.assertEqual((row["espn"], len(row["events"])), ("mma/ufc", 12))
        self.assertEqual({e["card_id"] for e in row["events"]}, {"600061266"})
        # Every bout starts within 36 hours of 13:00Z (the main card at 00:00Z Sept 27 is 35 hours out): one request each.
        asked = [call["url"] for call in fake.calls if call["url"].startswith(CORE_HOST)]
        self.assertEqual(len(asked), 12)
        self.assertTrue(all("/events/600061266/competitions/" in url and url.endswith("/odds") for url in asked))  # no predictor for MMA
        odds = store.latest({"odds": ["ufc"]}, self.clock())["odds"]["ufc"]
        priced = {e["id"]: e["lines"] for e in odds["events"]}
        self.assertEqual(len(priced), 12)
        self.assertEqual(sorted(bout for bout, lines in priced.items() if not lines), ["401914469", "401924683"])
        main = priced["401911630"][0]
        self.assertEqual((main["home_ml"], main["away_ml"], main["home_athlete"], main["away_athlete"]), (-155, 130, "5088844", "3075570"))
        self.assertTrue(all(e["fetched"] for e in odds["events"]))

    def test_ufc_is_a_league_the_feeds_know_and_the_unpriced_sports_stay_unmapped(self):
        self.assertEqual((feeds.league_of_series("KXUFCFIGHT"), feeds.SPORTS_LEAGUES["ufc"]), ("ufc", "mma/ufc"))
        self.assertEqual(requested({"sports": ["KXUFCFIGHT"], "odds": ["ufc"]}), {"sports": ["ufc"], "odds": ["ufc"]})
        self.assertEqual(request_feed("ufc_live_scores"), "sports")
        self.assertIsNone(request_feed("tennis_live_scores"))  # tennis has no line at ESPN: not recorded
        leagues, unmapped = feeds.sports_plan(niches.load())
        self.assertIn("ufc", leagues)
        self.assertTrue({"KXATPMATCH", "KXWTAMATCH", "KXT20MATCH"} <= set(unmapped))
        self.assertEqual(feeds.sports_days("ufc", epoch(NOW)), ["20260925", "20260926"])


# ------------------------------------------------------------------------------------- matching
class Names(unittest.TestCase):
    def test_one_person_by_name_never_by_a_surname_alone(self):
        same = (("Norma Dumont Viana", "Norma Dumont"),  # a compound surname one side shortens
                ("Alateng Heili", "Alatengheili"),  # the same letters run together
                ("Raul Rosas Jr", "Raul Rosas Jr."), ("Wang Cong", "Cong Wang"),  # a suffix; family name first
                ("A. Davidovich Fokina", "Alejandro Davidovich Fokina"),  # an initial
                ("Elena-Gabriela Ruse", "Elena Gabriela Ruse"), ("Jiří Veselý", "Jiri Vesely"), ("Sean O'Malley", "Sean OMalley"),
                ("Imanol Rodriguez Pillado", "Imanol Rodriguez"), ("Rafael Dos Anjos", "Rafael dos Anjos"))
        other = (("Luis Hernandez", "Alexander Hernandez"), ("Hernandez", "Luis Hernandez"), ("Valesca Machado", "Tina Black"),
                 ("Coleman Wong", "Chak Lam Coleman Wong"), ("Norma Dumont", "Norma Perez"), ("", "Norma Dumont"),
                 ("Luis Hernandez Garcia", "Luis Garcia Hernandez Lopez"))
        for a, b in same:
            self.assertTrue(SEED["same_person"](SEED["person"](a), SEED["person"](b)), (a, b))
        for a, b in other:
            self.assertFalse(SEED["same_person"](SEED["person"](a), SEED["person"](b)), (a, b))


class Matching(unittest.TestCase):
    """A market is priced only when exactly one bout on the board is the fight its ticker and title name."""

    def match(self, *rows, board=None):
        return SEED["match_bout"]([parse(t, title) for t, title in rows], SEED["bouts_of"](board or BOARD))

    def test_every_fight_of_the_recorded_card_is_matched_but_the_card_change(self):
        events = {}
        for row in RECORDED["markets"]:
            parsed = SEED["parse_h2h"](row)
            self.assertIsNotNone(parsed, row["market"])  # every recorded market reads
            events.setdefault(parsed["event"], []).append(parsed)
        self.assertEqual(len(events), 30)
        bouts, matched = SEED["bouts_of"](BOARD), {}
        for event, rows in events.items():
            hit = SEED["match_bout"](rows, bouts)
            if hit is None:
                continue
            matched[event] = hit[0]["id"]
            for parsed in rows:  # each code is the athlete its title names
                athlete = next(hit[0][side] for side in ("home", "away") if hit[0][side]["id"] == hit[1][parsed["code"]])
                self.assertTrue(SEED["same_person"](parsed["name"], SEED["person"](athlete["team"])), (parsed["ticker"], athlete))
        self.assertEqual(sorted(matched), sorted(f"KXUFCFIGHT-26SEP26{code}" for code in CARD_FIGHTS))
        self.assertEqual(len(set(matched.values())), len(matched))  # one bout is one Kalshi fight
        # The twelfth Sept 26 fight is a card change: Kalshi's "Amaya vs Machado" is ESPN's "Tina Black vs Melissa Amaya".
        self.assertIsNone(self.match(("KXUFCFIGHT-26SEP26AMAMAC-AMA", "Melissa Amaya wins"), ("KXUFCFIGHT-26SEP26AMAMAC-MAC", "Valesca Machado wins")))

    def test_what_a_ticker_and_title_say_and_when_they_disagree(self):
        row = parse("KXUFCFIGHT-26SEP26DUMPER-DUM", "Norma Dumont Viana wins")
        self.assertEqual((row["event"], row["date"], row["letters"], row["code"], row["name"], row["game"]),
                         ("KXUFCFIGHT-26SEP26DUMPER", (2026, 9, 26), "DUMPER", "DUM", ("norma", "dumont", "viana"), "KXUFCFIGHT:26SEP26DUMPER"))
        self.assertIsNone(parse("KXUFCFIGHT-26SEP26DEMJAU-JAU", "Vanessa Demopoulos wins"))  # the code is not the title's fighter
        self.assertIsNone(parse("KXUFCFIGHT-26SEP26DEMJAU-XYZ", "Xavier Yz wins"))  # a code not in the event's letters
        self.assertIsNone(parse("KXUFCFIGHT-26SEP26DEMJAU-DEM", "Demopoulos by knockout"))
        self.assertIsNone(parse("KXATPMATCH-26SEP25MEDROY-MED", "Daniil Medvedev wins"))  # no line to price tennis by

    def test_a_wrong_match_is_impossible(self):
        right = (("KXUFCFIGHT-26SEP26DEMJAU-DEM", "Vanessa Demopoulos wins"), ("KXUFCFIGHT-26SEP26DEMJAU-JAU", "Yazmin Jauregui wins"))
        self.assertEqual(self.match(*right)[1], {"DEM": "4683395", "JAU": "5063403"})
        # Another date: a day either way is the same fight (a card's local date), three days is not.
        self.assertIsNotNone(self.match(("KXUFCFIGHT-26SEP27DEMJAU-DEM", "Vanessa Demopoulos wins")))
        self.assertIsNone(self.match(("KXUFCFIGHT-26SEP29DEMJAU-DEM", "Vanessa Demopoulos wins")))
        # Two bouts of the same two fighters in the window: skipped.
        demopoulos = next(b for b in BOARD if b["id"] == "401914472")
        self.assertIsNone(self.match(*right, board=BOARD + [{**copy.deepcopy(demopoulos), "id": "999"}]))
        # A name that fits both fighters of a bout: skipped.
        both = copy.deepcopy(demopoulos)
        both["home"]["team"], both["away"]["team"] = "Luis Hernandez", "Luis Hernandez Garcia"
        self.assertIsNone(self.match(("KXUFCFIGHT-26SEP26HERGAR-HER", "Luis Hernandez wins"), board=[both]))
        # Two of Kalshi's names that are one fighter: skipped.
        self.assertIsNone(self.match(("KXUFCFIGHT-26SEP26DEMVAN-DEM", "Vanessa Demopoulos wins"), ("KXUFCFIGHT-26SEP26DEMVAN-VAN", "Vanessa Demopoulos wins")))
        # A fighter who is not in the bout.
        self.assertIsNone(self.match(("KXUFCFIGHT-26SEP26DEMSMI-SMI", "Jane Smith wins"), ("KXUFCFIGHT-26SEP26DEMSMI-DEM", "Vanessa Demopoulos wins")))

    def test_a_lone_market_needs_its_rivals_code_to_name_the_other_athlete(self):
        self.assertEqual(self.match(("KXUFCFIGHT-26SEP26DEMJAU-DEM", "Vanessa Demopoulos wins"))[1], {"DEM": "4683395"})
        self.assertIsNone(self.match(("KXUFCFIGHT-26SEP26DEMSMI-DEM", "Vanessa Demopoulos wins")))  # SMI is not Jauregui
        # ESPN's "Alatengheili" begins no word with HEI: alone, John Castaneda's market is not priced ...
        self.assertIsNone(self.match(("KXUFCFIGHT-26SEP26CASHEI-CAS", "John Castaneda wins")))
        # ... and with Kalshi's "Alateng Heili" beside it, the fight is found.
        self.assertIsNotNone(self.match(("KXUFCFIGHT-26SEP26CASHEI-CAS", "John Castaneda wins"), ("KXUFCFIGHT-26SEP26CASHEI-HEI", "Alateng Heili wins")))


# ---------------------------------------------------------------------------------------- pricing
class Pricing(unittest.TestCase):
    def bout(self, bout_id: str) -> dict:
        return copy.deepcopy(next(b for b in BOARD if b["id"] == bout_id))

    def test_the_de_vigged_moneyline_leans_to_half_by_the_draw_and_no_contest_share(self):
        main = self.bout("401911630")  # Rosas Jr. -155, Barcelos +130
        fair = SEED["bout_fair"]({"lines": LINES["401911630"]}, main, 0.015)
        self.assertAlmostEqual(fair["5088844"], 0.583 + 0.015 * (0.5 - 0.583))
        self.assertAlmostEqual(fair["3075570"], 0.417 + 0.015 * (0.5 - 0.417))
        self.assertAlmostEqual(sum(fair.values()), 1.0)
        self.assertAlmostEqual(SEED["bout_fair"]({"lines": LINES["401911630"]}, main, 0.0)["5088844"], 0.583)

    def test_prices_follow_the_athletes_ids_never_home_and_away(self):
        main = self.bout("401911630")
        main["home"], main["away"] = main["away"], main["home"]  # the board lists them the other way round
        self.assertAlmostEqual(SEED["bout_fair"]({"lines": LINES["401911630"]}, main, 0.0)["5088844"], 0.583)
        foreign = copy.deepcopy(LINES["401911630"])
        foreign[0]["home_athlete"] = "1"
        self.assertIsNone(SEED["bout_fair"]({"lines": foreign}, main, 0.0))  # a line about someone else
        bare = [{k: v for k, v in LINES["401911630"][0].items() if k not in ("home_athlete", "away_athlete")}]
        self.assertIsNone(SEED["bout_fair"]({"lines": bare}, main, 0.0))  # no ids: not guessed from home and away
        second = copy.deepcopy(LINES["401911630"][0])
        second.update(provider="Other", implied_home=0.603, implied_away=0.397)
        self.assertAlmostEqual(SEED["bout_fair"]({"lines": LINES["401911630"] + [second]}, main, 0.0)["5088844"], 0.593)  # the mean


# ---------------------------------------------------------------------------------------- entries
class Entries(SeedCase):
    DUM, PER = "KXUFCFIGHT-26SEP26DUMPER-DUM", "KXUFCFIGHT-26SEP26DUMPER-PER"

    def run_seed(self, ctx, seed=None):
        out = runner.decide(code(), ctx)
        self.assertTrue(out.get("ok"), out.get("error"))
        self._check(out, ctx)
        return out

    def order(self, ticker=None, price=0.41, sent="2026-09-25T12:50:00.000Z", leg="yes"):
        return {"order_id": "ord-1", "market": ticker or self.DUM, "leg": leg, "side": "buy", "quantity": 24, "limit_price": price,
                "submitted_at": sent}

    def test_on_the_recorded_card_it_bids_only_the_fight_off_the_line(self):
        out = self.run_seed(ctx_for())
        # Dumont Viana vs Perez: the line says Perez 0.5635 (0.5625 with the void share), Kalshi 0.58/0.59. The YES of
        # Dumont Viana at the bid, 0.41, clears the 2-cent edge (no maker fee on KXUFCFIGHT); every other fight is within it.
        self.assertEqual([(i["market"], i["leg"], i["limit_price"], i["quantity"], i.get("post_only")) for i in out["intents"]],
                         [(self.DUM, "yes", 0.41, 24, True)])
        self.assertIn("UFC: priced 18 of 24 markets on 9 matched fights (2 no line, 1 unmatched)", out["thought"])
        self.assertEqual(out["memory"]["starts"], {"KXUFCFIGHT-26SEP26DUMPER": "2026-09-27T00:00:00Z"})
        self.assertEqual(out["memory"]["fair"][self.DUM], 0.4375)

    def test_stale_lines_or_a_bout_about_to_start_place_nothing(self):
        out = self.run_seed(ctx_for(fetched="2026-09-25T11:00:00.000Z"))
        self.assertEqual(out["intents"], [])
        self.assertIn("stale lines", out["thought"])
        # 20:45Z Sept 26: the prelims start in 15 minutes and are left alone; the main card (00:00Z) is still priced.
        late = "2026-09-26T20:45:00.000Z"
        out = self.run_seed(ctx_for(late))
        self.assertIn("starting", out["thought"])
        main_card = {f"KXUFCFIGHT-26SEP26{code}" for code in ("AMAMAC", "OSMUUL", "HERDUM", "DUMPER", "ROSBAR")}  # 00:00Z Sept 27
        self.assertTrue(out["intents"])
        self.assertTrue(all(intent["market"].rsplit("-", 1)[0] in main_card for intent in out["intents"]), out["intents"])

    def test_it_takes_the_ask_only_far_off_the_line_and_never_after_a_refusal(self):
        rows = shown()
        jau = next(m for m in rows if m["market"] == "KXUFCFIGHT-26SEP26DEMJAU-JAU")
        jau.update(yes_bid=0.70, yes_ask=0.78)  # the line says 0.8625
        out = self.run_seed(ctx_for(markets=rows))
        first = out["intents"][0]
        self.assertEqual((first["market"], first["leg"], first["limit_price"], first.get("post_only")), (jau["market"], "yes", 0.78, None))
        refused = [{"status": "refused", "reason": "post-only until the taker record is positive", "instrument": {"market_id": jau["market"]}}]
        out = self.run_seed(ctx_for(markets=rows, recent_order_outcomes=refused))
        first = out["intents"][0]
        self.assertEqual((first["market"], first["limit_price"], first.get("post_only")), (jau["market"], 0.71, True))

    def test_one_market_a_fight_never_both_sides(self):
        held = [{"market": self.DUM, "leg": "yes", "quantity": 24, "average_cost": 0.41}]
        out = self.run_seed(ctx_for(positions=held))
        self.assertFalse([i for i in out["intents"] if i["market"].startswith("KXUFCFIGHT-26SEP26DUMPER")])

    def test_a_resting_bid_is_cancelled_when_the_line_moves_the_edge_goes_or_the_bout_nears(self):
        memory = {"starts": {"KXUFCFIGHT-26SEP26DUMPER": "2026-09-27T00:00:00Z"}, "fair": {self.DUM: 0.4375}}
        self.assertEqual(self.run_seed(ctx_for(open_orders=[self.order()], memory=memory))["cancels"], [])
        moved = {**memory, "fair": {self.DUM: 0.45}}
        self.assertEqual(self.run_seed(ctx_for(open_orders=[self.order()], memory=moved))["cancels"], ["ord-1"])
        self.assertEqual(self.run_seed(ctx_for(open_orders=[self.order(price=0.43)], memory=memory))["cancels"], ["ord-1"])  # 0.8c: under half
        near = ctx_for("2026-09-26T23:45:00.000Z", open_orders=[self.order()], memory=memory, markets=[])
        near["feeds"] = {}
        self.assertEqual(self.run_seed(near)["cancels"], ["ord-1"])  # 15 minutes out, shown or not, feeds or not
        amaya = self.order("KXUFCFIGHT-26SEP26AMAMAC-AMA", price=0.30)
        self.assertEqual(self.run_seed(ctx_for(open_orders=[amaya]))["cancels"], ["ord-1"])  # a fight it cannot price


# ---------------------------------------------------------------------------------------- the founder
class Founder(unittest.TestCase):
    def test_a_seeds_row_at_the_end_and_its_own_family(self):
        row = seeds.SEEDS[-1]
        self.assertEqual((row["name"], row["family"], row["file"]), ("h2h-ufc", "sports-h2h-ufc", "sports_h2h.py"))
        self.assertIn("Unmeasured", row["why"])

    def test_seated_on_the_sports_desk_with_its_feeds_and_bounded_knobs(self):
        desk = niches.load()["kalshi-sports"]
        self.assertEqual(desk.max_members, 25)
        self.assertEqual(desk.founders[-1]["key"], "h2h-ufc")
        row = founder()
        self.assertEqual((row["seed"], row["seat_full_league"], row["seat_priority"]), ("h2h-ufc", True, 80))
        self.assertTrue(desk.fits("KXUFCFIGHT") and "KXUFCFIGHT" in desk.universe and "KXUFCFIGHT" not in desk.maker_fee_series)
        source = code()
        check_code(source)
        described = runner.needs_of(source)
        self.assertTrue(described["ok"], described)
        needs, params = described["needs"], described["params"]
        self.assertEqual((needs["venue"], needs["horizon"], needs["style"], needs["series"]), ("kalshi", "day", "model-versus-market", ["KXUFCFIGHT"]))
        self.assertEqual(needs["feeds"], {"odds": ["ufc"], "sports": ["ufc"]})
        self.assertEqual((needs["min_hours_to_close"], needs["max_hours_to_close"], needs["max_markets"]), (0.5, 42, 200))
        self.assertLessEqual(needs["max_hours_to_close"], 48)  # the day horizon's rule
        report = parameters.inspect(params, needs)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["frozen"], [])
        for trial in range(20):
            self.assertTrue(parameters.inspect(parameters.mutate(params, seed=f"ufc:{trial}", needs=needs), needs)["valid"])


if __name__ == "__main__":
    unittest.main()
