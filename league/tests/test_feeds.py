"""Feeds: ESPN scoreboards and perpetual funding recorded with the House's receive time, and
Deribit's DVOL and OKX's settled funding as backfilled point-in-time history.

Sept 22, 2026: 43 agents had asked for live sports scores and 32 for perp funding or open
interest, and nothing in the league supplied either. These tests hold the recorder to its three
rules -- point in time, nothing fabricated, unchanged content stored once -- and the House to its
hooks: `ctx["feeds"]` only when declared, a replay only once the feeds are recorded long enough
(and no trial before), a lane of its own that runs while paused, and a block in health.json.

Sept 23, 2026: every Alpaca crypto strategy failed replay after fees and the live feeds could not
be replayed for a day. `vol` and `funding` are fetched as history, each row stamped when it became
final: the tests below hold the backfill to that stamp, to resuming without fetching a page twice,
to derived fields that read only the past, and a strategy that declares them to a replay at once.
"""

import json
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime
from pathlib import Path

from league import feeds, niches
from league.commons import Commons
from league.feeds import FeedRecorder, request_feed, requested
from league.ledger import Ledger
from league.replay import run_replay
from league.tests.test_house import BUYER, HouseCase
from ltcm.data.derivs import zscore
from ltcm.tests import test_data_derivs as derivs
from ltcm.tests.fakes import Clock, FakeTransport, TransportError
from ltcm.tests.test_data_sports import EPL, EPL_JSON, HOST, NFL, SCOREBOARD_JSON


def epoch(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def okx_for(payload, coins=("BTC", "ETH")):
    """An OKX route that answers for `coins` and says "no such instrument" for any other."""
    def answer(method, url, body):
        if any(f"{coin}-USDT-SWAP" in url for coin in coins):
            return payload
        return {"code": "51001", "data": [], "msg": "Instrument ID does not exist"}
    return answer


def transport(**overrides) -> FakeTransport:
    routes = {NFL: SCOREBOARD_JSON, EPL: EPL_JSON,
              derivs.DVOL: derivs.DVOL_JSON, derivs.OKX_FUNDING: okx_for(derivs.OKX_FUNDING_JSON),
              derivs.OKX_HISTORY: okx_for(derivs.OKX_HISTORY_JSON), derivs.OKX_OI: okx_for(derivs.OKX_OI_JSON),
              derivs.OKX_TICKER: okx_for(derivs.OKX_TICKER_JSON), derivs.HYPERLIQUID: derivs.HYPERLIQUID_JSON,
              derivs.KRAKEN: derivs.KRAKEN_JSON}
    routes.update(overrides)
    return FakeTransport(routes)


def recorded_board(name: str) -> dict:
    """An ESPN scoreboard recorded Sept 25, 2026 and trimmed to the fields `event_row` reads
    (ltcm/tests/fixtures/feeds/espn_scoreboard_*.json)."""
    return json.loads((Path(__file__).resolve().parents[2] / "ltcm" / "tests" / "fixtures" / "feeds" / name).read_text(encoding="utf-8"))


def perp_row(rate: float) -> dict:
    return {"symbol": "BTC", "okx": {"rate": rate, "open_interest_usd": 2.2e9}, "hyperliquid": None, "kraken": None,
            "dvol": 34.4, "funding_z": 0.5, "funding_history_n": 30}


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock("2026-09-22T12:00:00Z")
        self.alerts = []
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)

    def recorder(self, keys, transports=None, **kw) -> FeedRecorder:
        recorder = FeedRecorder(path=Path(self.dir.name) / "feeds.sqlite", transports=transports, clock=self.clock, ledger=self.ledger,
                                alert=lambda level, text: self.alerts.append((level, text)), keys=keys, **kw)
        self.addCleanup(recorder.close)
        return recorder


class Store(StoreCase):
    def test_a_row_is_never_visible_before_it_was_received(self):
        store = self.recorder({"perps": ["BTC"]})
        t0 = self.clock()
        store.record("perps", "BTC", started=t0, finished=t0 + 1.2341, payload=perp_row(0.0001))  # received 12:00:01.235
        store.record("perps", "BTC", started=t0 + 599, finished=t0 + 600, payload=perp_row(0.0002))
        wanted = {"perps": ["BTC"]}
        self.assertEqual(store.latest(wanted, t0 + 1.2341), {})  # received a fraction of a millisecond later: not yet
        first = store.latest(wanted, t0 + 1.235)["perps"]["BTC"]
        self.assertEqual((first["t"], first["okx"]["rate"]), ("2026-09-22T12:00:01.235Z", 0.0001))
        self.assertEqual(store.latest(wanted, t0 + 599.999)["perps"]["BTC"]["okx"]["rate"], 0.0001)
        self.assertEqual(store.latest(wanted, "2026-09-22T12:10:00.000Z")["perps"]["BTC"]["okx"]["rate"], 0.0002)
        # A tape ending before the second row was received does not carry it; one starting after the
        # first opens with it, stamped when it was received.
        early = store.series(wanted, t0 - 3600, t0 + 300, 300)["perps"]["BTC"]
        self.assertEqual([row["okx"]["rate"] for row in early], [0.0001])
        late = store.series(wanted, t0 + 30, t0 + 3600, 300)["perps"]["BTC"]
        self.assertEqual([(row["t"], row["okx"]["rate"]) for row in late],
                         [("2026-09-22T12:00:01.235Z", 0.0001), ("2026-09-22T12:10:00.000Z", 0.0002)])
        self.assertEqual(store.series(wanted, t0 - 7200, t0 - 3600, 300), {})

    def test_the_replay_shows_a_row_only_from_when_it_was_received(self):
        store = self.recorder({"perps": ["BTC"]})
        t0 = self.clock()
        store.record("perps", "BTC", started=t0, finished=t0 + 1.2341, payload=perp_row(0.0001))
        store.record("perps", "BTC", started=t0 + 599, finished=t0 + 600, payload=perp_row(0.0002))
        code = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "t", "symbols": ["BTC/USD"], "bars": {"timeframe": "5Min", "limit": 5},
         "feeds": {"perps": ["BTC"]}}
PARAMS = {}
def decide(ctx):
    row = ((ctx.get("feeds") or {}).get("perps") or {}).get("BTC")
    seen = list((ctx.get("memory") or {}).get("seen") or [])
    seen.append([ctx["now"], None if row is None else row["okx"]["rate"], "feeds" in ctx])
    if row is not None:
        row["okx"]["rate"] = -1.0
    return {"intents": [], "memory": {"seen": seen}}
'''
        times = ["2026-09-22T12:00:00Z", "2026-09-22T12:00:01Z", "2026-09-22T12:00:02Z", "2026-09-22T12:09:59Z",
                 "2026-09-22T12:10:00Z", "2026-09-22T12:15:00Z"]
        tape = {"venue": "alpaca", "horizon": "hour", "step_seconds": 1,
                "steps": [{"t": t, "bars": {"BTC/USD": {"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}}} for t in times],
                "feeds": store.series({"perps": ["BTC"]}, "2026-09-22T11:00:00Z", "2026-09-22T13:00:00Z", 1)}
        result = run_replay(code, {}, tape, stake=100.0, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["errors"], 0)
        # Nothing before 12:00:01.235, the first row until 12:10:00, and a strategy that edits what it
        # is shown does not edit what a later step sees.
        self.assertEqual(result["final_memory"]["seen"], [[times[0], None, True], [times[1], None, True], [times[2], 0.0001, True],
                                                          [times[3], 0.0001, True], [times[4], 0.0002, True], [times[5], 0.0002, True]])
        undeclared = run_replay(code.replace('"feeds": {"perps": ["BTC"]}', '"style2": "x"'), {}, tape, stake=100.0, audit=True)
        self.assertEqual([step[2] for step in undeclared["final_memory"]["seen"]], [False] * 6)  # only what is declared is shown

    def test_unchanged_content_is_stored_once_and_every_poll_still_counts(self):
        store = self.recorder({"perps": ["BTC"]})
        t0 = self.clock()
        for offset, rate in ((0, 0.0001), (300, 0.0001), (600, 0.0001), (900, 0.0002), (1200, 0.0001)):
            store.record("perps", "BTC", started=t0 + offset - 1, finished=t0 + offset, payload=perp_row(rate))
        self.assertFalse(store.record("perps", "BTC", started=t0 + 1499, finished=t0 + 1500, error="TransportError: down"))
        row = store.coverage({"perps": ["BTC"]})["perps"]["BTC"]
        self.assertEqual((row["polls"], row["ok"], row["snapshots"]), (6, 5, 3))
        self.assertEqual(row["last_error"], "TransportError: down")
        rows = store.series({"perps": ["BTC"]}, t0 - 1, t0 + 3600, 1)["perps"]["BTC"]
        self.assertEqual([(r["t"][11:19], r["okx"]["rate"]) for r in rows],
                         [("12:00:00", 0.0001), ("12:15:00", 0.0002), ("12:20:00", 0.0001)])  # t: when that content was FIRST received
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM polls WHERE ok = 0").fetchone()[0], 1)
        reopened = FeedRecorder(path=store.path, clock=self.clock, keys={"perps": ["BTC"]})  # the counters come back from the store
        self.addCleanup(reopened.close)
        again = reopened.coverage({"perps": ["BTC"]})["perps"]["BTC"]
        self.assertEqual((again["polls"], again["ok"], again["snapshots"], again["last_error"]), (6, 5, 3, "TransportError: down"))

    def test_threads_get_their_own_connection_and_a_finished_threads_is_closed(self):
        store = self.recorder({"perps": ["BTC"]})
        store.record("perps", "BTC", started=self.clock(), finished=self.clock(), payload=perp_row(0.0001))
        seen = []
        workers = [threading.Thread(target=lambda: seen.append(len(store.latest({"perps": ["BTC"]}, self.clock())))) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(seen, [1, 1, 1, 1])
        store.db.execute("SELECT 1")  # the main thread's own, still open
        last = threading.Thread(target=lambda: store.series({"perps": ["BTC"]}, 0, self.clock(), 300))
        last.start()
        last.join()
        self.assertEqual(len(store._connections), 2)  # the four finished workers' connections were closed

    def test_a_long_key_is_sampled_coarser_to_fit_the_tape_and_never_later(self):
        store = self.recorder({"perps": ["BTC"]})
        t0 = self.clock()
        received = [t0 + 60 * i + 7 for i in range(60)]
        for i, at in enumerate(received):
            store.record("perps", "BTC", started=at - 1, finished=at, payload=perp_row(i / 1e6))
        by_step = store.series({"perps": ["BTC"]}, t0, t0 + 3600, 300)["perps"]["BTC"]
        self.assertEqual(len(by_step), 12)  # one row a five-minute step: the last received in it
        self.assertEqual(by_step[0]["okx"]["rate"], 4 / 1e6)
        small = store.series({"perps": ["BTC"]}, t0, t0 + 3600, 60, max_bytes=4000)["perps"]["BTC"]
        self.assertLess(len(small), 60)
        stamps = {feeds.stamp(at) for at in received}
        self.assertTrue(all(row["t"] in stamps for row in small))  # a coarser view of what was received, nothing new


class Recorder(StoreCase):
    def test_scoreboards_of_the_mapped_leagues_are_polled_and_a_past_date_is_never_asked(self):
        fake = transport()
        store = self.recorder({"sports": ["nfl", "epl"]}, transports={"sports": fake})
        self.assertTrue(store.due())
        out = store.run()
        self.assertEqual(out["polled"], ["sports:nfl", "sports:epl"])
        # The NFL's board is its week; a daily league's board (EPL) is joined by the boards of the New
        # York days the next 36 hours reach (08:00 New York, Sept 22: that day and the next), never a past one.
        self.assertEqual([call["url"] for call in fake.calls], [NFL, EPL, EPL + "?dates=20260922", EPL + "?dates=20260923"])
        self.assertTrue(all(call["query"].get("dates", "20260922") >= "20260922" for call in fake.calls))
        board = store.latest({"sports": ["nfl", "epl"]}, self.clock())["sports"]
        self.assertEqual((board["nfl"]["espn"], [e["id"] for e in board["nfl"]["events"]]), ("football/nfl", ["401872932", "401872933"]))
        self.assertEqual((board["epl"]["events"][0]["status"], board["epl"]["events"][0]["home"]["score"]), ("in", 1))
        self.assertEqual(board["nfl"]["t"], "2026-09-22T12:00:00.000Z")

    def test_college_football_is_the_fbs_and_fcs_weeks_together(self):
        # Sept 25, 2026: the default board was ESPN's 18 featured games while Kalshi listed 113 NCAAF
        # spread events; the FBS (groups=80) and FCS (groups=81) week boards held all of them. The
        # fixtures are four games of each, recorded that morning, one of them (Howard at Rutgers) on both.
        cfb = HOST + "/apis/site/v2/sports/football/college-football/scoreboard"
        fbs, fcs = recorded_board("espn_scoreboard_ncaaf_groups80.json"), recorded_board("espn_scoreboard_ncaaf_groups81.json")
        fake = transport(**{cfb: lambda method, url, body: fbs if "groups=80" in url else fcs if "groups=81" in url else {"events": []}})
        store = self.recorder({"sports": ["ncaaf"]}, transports=fake)
        store.run()
        self.assertEqual([call["query"] for call in fake.calls], [{"groups": "80", "limit": "300"}, {"groups": "81", "limit": "300"}])
        events = store.latest({"sports": ["KXNCAAFSPREAD"]}, self.clock())["sports"]["ncaaf"]["events"]
        self.assertEqual(len(events), 7)  # 4 + 4, the game on both boards once
        self.assertEqual([e["short_name"] for e in events if e["id"] == "401858468"], ["HOW @ RUTG"])
        self.assertEqual(feeds.sports_days("ncaaf", self.clock()), [])  # a week board: no dated board is asked

    def test_a_daily_board_is_joined_by_today_and_the_next_days_board(self):
        # 06:18Z Sept 25, 2026: ESPN's default MLB board was still Sept 24 (every game final), so the
        # day's games and the next day's were on no board. The row joins the dated boards of today and
        # tomorrow (New York); tomorrow's is read again every 15 minutes, today's at every poll until
        # the default board shows it.
        self.clock.set(epoch("2026-09-25T06:18:00Z"))
        mlb = HOST + "/apis/site/v2/sports/baseball/mlb/scoreboard"
        boards = {"": recorded_board("espn_scoreboard_mlb_default_20260924.json"),
                  "dates=20260925": recorded_board("espn_scoreboard_mlb_20260925.json"),
                  "dates=20260926": recorded_board("espn_scoreboard_mlb_20260926.json")}
        fake = transport(**{mlb: lambda method, url, body: boards[urllib.parse.urlsplit(url).query]})
        store = self.recorder({"sports": ["mlb"]}, transports=fake)
        store.run()
        self.assertEqual([call["url"] for call in fake.calls], [mlb, mlb + "?dates=20260925", mlb + "?dates=20260926"])
        row = store.latest({"sports": ["mlb"]}, self.clock())["sports"]["mlb"]
        self.assertEqual([e["status"] for e in row["events"]], ["post", "post", "pre", "pre", "pre", "pre", "pre", "pre"])
        self.assertEqual(row["events"][2]["home"]["short"], "Red Sox")
        store._schedule("sports", "mlb", 0.0)  # due again within the quarter hour
        self.clock.advance(120)
        store.run()
        self.assertEqual([call["url"] for call in fake.calls[3:]], [mlb, mlb + "?dates=20260925"])  # tomorrow's is kept
        self.assertEqual(len(store.latest({"sports": ["mlb"]}, self.clock())["sports"]["mlb"]["events"]), 8)
        boards[""] = {**boards["dates=20260925"], "day": {"date": "2026-09-25"}}  # the default board turns to today
        self.clock.advance(15 * 60)
        store._schedule("sports", "mlb", 0.0)
        store.run()
        self.assertEqual([call["url"] for call in fake.calls[5:]], [mlb, mlb + "?dates=20260926"])  # today's is the board itself
        self.assertEqual(feeds.sports_days("mlb", epoch("2026-09-25T20:00:00Z")), ["20260925", "20260926", "20260927"])

    def test_a_live_board_is_polled_every_minute_and_a_quiet_one_every_quarter_hour(self):
        soon = {"events": [{"id": "9", "name": "A at B", "date": "2026-09-22T13:00Z", "competitions": [{
            "competitors": [{"homeAway": "home", "score": "0", "team": {"displayName": "B"}},
                            {"homeAway": "away", "score": "0", "team": {"displayName": "A"}}],
            "status": {"type": {"state": "pre"}}}]}]}
        mlb = HOST + "/apis/site/v2/sports/baseball/mlb/scoreboard"
        fake = transport(**{mlb: soon})
        store = self.recorder({"sports": ["nfl", "epl", "mlb"]}, transports=fake)
        store.run()
        self.clock.advance(61)
        self.assertEqual(store.run()["polled"], ["sports:epl", "sports:mlb"])  # a game on, and one starting within the hour
        self.clock.advance(60)
        self.assertEqual(store.run()["polled"], ["sports:epl", "sports:mlb"])
        self.clock.advance(780)  # 15 minutes and a second after the first pass
        self.assertEqual(store.run()["polled"], ["sports:nfl", "sports:epl", "sports:mlb"])
        self.assertFalse(store.due())
        self.assertEqual(store.health()["sports"]["live_boards"], ["epl", "mlb"])

    def test_perps_record_each_coin_and_a_coin_no_venue_answers_is_a_failed_poll(self):
        fake = transport()
        store = self.recorder({"perps": ["BTC", "ETH", "DOGE"]}, transports={"perps": fake})
        out = store.run()
        self.assertEqual(out["polled"], ["perps"])
        self.assertEqual(out["failed"], [("perps", "DOGE", "no venue answered for DOGE")])
        rows = store.latest({"perps": ["BTC", "ETH", "DOGE"]}, self.clock())["perps"]
        self.assertEqual(sorted(rows), ["BTC", "ETH"])  # DOGE is absent: unavailable, never a row of Nones
        btc = rows["BTC"]
        self.assertNotIn("as_of", btc)  # the receive stamp `t` replaces the fetch's own clock
        self.assertEqual((btc["okx"]["open_interest_usd"], btc["hyperliquid"]["open_interest"], btc["kraken"]["symbol"], btc["dvol"]),
                         (2232794658.58, 35483.64326, "PF_XBTUSD", 34.37))
        self.assertIsNone(rows["ETH"]["kraken"])
        doge = store.coverage({"perps": ["DOGE"]})["perps"]["DOGE"]
        self.assertEqual((doge["polls"], doge["ok"], doge["first_ok"]), (1, 0, None))
        self.assertEqual(store.health()["perps"]["venues_answering"], {"okx": 2, "hyperliquid": 2, "kraken": 1})
        self.clock.advance(299)
        self.assertFalse(store.due())
        self.clock.advance(1)
        self.assertTrue(store.due())  # every five minutes

    def test_a_venue_that_is_down_is_a_failed_poll_raises_nothing_and_warns_at_most_hourly(self):
        down = FakeTransport(default=TransportError("the host is down"))
        store = self.recorder({"sports": ["nfl"], "perps": ["BTC", "ETH"]}, transports=down)
        out = store.run()
        self.assertEqual(sorted((feed, key) for feed, key, _ in out["failed"]), [("perps", "BTC"), ("perps", "ETH"), ("sports", "nfl")])
        self.assertEqual(store.latest({"sports": ["nfl"], "perps": ["BTC"]}, self.clock()), {})
        self.assertEqual(store.db.execute("SELECT COUNT(*), SUM(ok) FROM polls").fetchone(), (3, 0))
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)
        self.assertEqual(sorted(level for level, _ in self.alerts), ["warning", "warning"])  # one a feed
        self.clock.advance(301)
        store.run()
        self.assertEqual(len(self.alerts), 2)  # not again within the hour
        # A fetcher that raises something nobody expected is a failed poll too, never an exception.
        store._fetchers.clear()
        store._transports = FakeTransport(default=RuntimeError("something nobody expected"))
        self.clock.advance(3600)
        out = store.run()
        self.assertEqual(len(out["failed"]), 3)
        self.assertIn("RuntimeError", dict(((f, k), e) for f, k, e in out["failed"])[("perps", "BTC")])
        self.assertEqual(len(self.alerts), 4)
        self.assertTrue(all(level == "warning" for level, _ in self.alerts))  # never "error": that rolls a release back

    def test_coverage_goes_to_the_ledger_at_most_hourly_per_feed(self):
        store = self.recorder({"sports": ["nfl"], "perps": ["BTC"]}, transports=transport())
        store.run()
        rows = [e.payload for e in self.ledger.iter(kinds="data.coverage")]
        self.assertEqual(sorted(r["feed"] for r in rows), ["perps", "sports"])
        sports = next(r for r in rows if r["feed"] == "sports")
        self.assertEqual((sports["asset"], sports["status"], sports["start"]), ("feed", "current", "2026-09-22T12:00:00.000Z"))
        self.assertEqual(sports["keys"]["nfl"]["snapshots"], 1)
        self.assertIn("KXT20MATCH", sports["unmapped_series"])  # reported as unavailable, never guessed
        self.clock.advance(901)
        store.run()
        self.assertEqual(self.ledger.count(kinds="data.coverage"), 2)
        self.clock.advance(3600)
        store.run()
        self.assertEqual(self.ledger.count(kinds="data.coverage"), 4)

    def test_what_is_polled_follows_the_desks(self):
        desks = niches.load()
        leagues, unmapped = feeds.sports_plan(desks)
        self.assertTrue({"nfl", "ncaaf", "mlb", "wnba", "nba", "nhl", "mls", "epl"} <= set(leagues))
        self.assertIn("KXT20MATCH", unmapped)
        self.assertNotIn("KXNFLGAME", unmapped)
        self.assertEqual([feeds.league_of_series(s) for s in ("KXNCAAFGAME", "KXWNBASPREAD", "KXNBAGAME", "KXMLBHR", "KXLOLGAME")],
                         ["ncaaf", "wnba", "nba", "mlb", None])
        self.assertTrue(all(league in feeds.SPORTS_LEAGUES for _, league in feeds.SPORTS_SERIES))
        coins = feeds.perp_coins(desks)
        self.assertTrue({"BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "LTC", "LINK", "BNB", "HYPE", "ZEC"} <= set(coins))
        self.assertNotIn("CRYPTOLEAD", coins)
        self.assertEqual(len(coins), len(set(coins)))


class Requests(StoreCase):
    def test_needs_feeds_are_held_to_known_names_six_keys_and_one_case(self):
        self.assertEqual(requested({"Sports": ["NFL", "KXEPLGAME", "football/college-football", "cricket", "nfl"],
                                    "PERPS": ["btc/usd", "XBT", "ethusdt", "PEPE"], "fog": ["KXHIGHNY"]}),  # (weather is recorded since Sept 24)
                         {"sports": ["nfl", "epl", "ncaaf"], "perps": ["BTC", "ETH"]})
        self.assertEqual(len(requested({"perps": sorted(feeds.known_perps())})["perps"]), 6)
        self.assertEqual(requested({"sports": "mlb"}), {"sports": ["mlb"]})
        self.assertEqual((requested(["nfl"]), requested(None), requested({"sports": ["xfl"]})), ({}, {}, {}))
        sports = niches.load()["kalshi-sports"]
        out = niches.constrain({"venue": "kalshi", "horizon": "day", "series": ["KXNFLGAME"],
                                "feeds": {"sports": ["KXNFLGAME", "NBA"], "perps": ["sol"], "odds": ["x"]}}, sports)
        self.assertEqual(out["feeds"], {"sports": ["nfl", "nba"], "perps": ["SOL"]})  # not held to the specialty
        self.assertNotIn("feeds", niches.constrain({"venue": "kalshi", "horizon": "day", "series": ["KXNFLGAME"],
                                                    "feeds": {"sports": ["curling"]}}, sports))

    def test_only_requests_that_plainly_name_a_recorded_feed_are_fulfilled_once(self):
        self.assertEqual({name: request_feed(name) for name in (
            "live_sports_scores", "espn_scoreboard", "live_game_state", "nfl_scores", "perp_funding_rates", "funding_rate_feed",
            "perpetual_open_interest", "okx_funding", "kalshi_open_interest_history", "player_injury_reports", "sports_live_data",
            "tennis_live_scores", "research_funding", "historical_scores")},
            {"live_sports_scores": "sports", "espn_scoreboard": "sports", "live_game_state": "sports", "nfl_scores": "sports",
             "perp_funding_rates": "perps", "funding_rate_feed": "perps", "perpetual_open_interest": "perps", "okx_funding": "perps",
             "kalshi_open_interest_history": None, "player_injury_reports": None, "sports_live_data": None,
             "tennis_live_scores": None, "research_funding": None, "historical_scores": None})
        commons = Commons(self.ledger, clock=self.clock)
        why = "the strategy needs this to price the contract it trades"
        ids = {name: commons.request_tool("carry-1", name, why)["queued"]
               for name in ("live_sports_scores", "perp_funding_rates", "kalshi_open_interest_history", "funding_rate_feed")}
        self.ledger.append("tool.blocked", {"request": ids["funding_rate_feed"], "outcome": "not a pure tool: the House has no feed"})
        store = self.recorder({"sports": ["nfl"], "perps": ["BTC"]})
        self.assertEqual(store.fulfil_requests(commons), [])  # nothing recorded yet: nothing has shipped
        store.record("perps", "BTC", started=self.clock(), finished=self.clock(), payload=perp_row(0.0001))
        self.assertEqual(sorted(store.fulfil_requests(commons)), sorted([ids["perp_funding_rates"], ids["funding_rate_feed"]]))
        store.record("sports", "nfl", started=self.clock(), finished=self.clock(), payload={"league": "nfl", "events": []})
        self.assertEqual(store.fulfil_requests(commons), [ids["live_sports_scores"]])
        self.assertEqual(store.fulfil_requests(commons), [])  # idempotent
        status = {row["id"]: row["status"] for row in commons._requests()}
        self.assertEqual(status[ids["kalshi_open_interest_history"]], "open")  # a Kalshi market's open interest is not a perp's
        answer = self.ledger.last("tool.fulfilled").payload
        self.assertTrue(answer["outcome"].startswith("Shipped"))
        self.assertIn("ctx['feeds']['sports']", answer["outcome"])


MOVE = {"markets": {"KXHIGHNY-26SEP22-B72.5": {"move_p5": 0.1234, "move_p15": 0.2345, "move_p60": 0.3456}},
        "model": "move-v1-20260924"}


class MoveFeed(StoreCase):
    """J1's move feature (the Jev-senses run, Sept 25, 2026): a live feed the House's own move sensor
    records per Kalshi series (league/jev_features.py), never polled by the feeds lane, held to the
    same three rules as every live feed."""

    def test_move_is_a_live_feed_without_a_host_keyed_by_kalshi_series(self):
        self.assertIn("move", feeds.FEEDS)
        self.assertNotIn("move", feeds.HISTORY_FEEDS)
        source = feeds.RECORDERS["move"]
        self.assertEqual((source.host, source.internal, feeds.GAP_SECONDS["move"]), ("", True, 900.0))
        self.assertTrue(feeds.WHAT["move"].startswith("not served until the Jev run's ship rule passes"))
        self.assertIn("nothing is back-filled", feeds.POINT_IN_TIME["move"])
        self.assertEqual(requested({"Move": ["kxhighny", "KXHIGHNY-26SEP22-B72.5", "KXBTCD", "", None, "not a series!", 7]}),
                         {"move": ["KXHIGHNY", "KXBTCD"]})  # a ticker names its series; anything else is dropped
        self.assertEqual(requested({"move": "KXBTCD"}), {"move": ["KXBTCD"]})
        self.assertEqual(len(requested({"move": [f"KXS{n}" for n in range(10)]})["move"]), feeds.MAX_KEYS)
        self.assertIsNone(request_feed("move_probability"))  # no tool request is answered with it

    def test_a_series_never_recorded_is_absent_and_a_row_is_seen_only_from_its_t(self):
        store = self.recorder(None)
        t0 = self.clock()
        wanted = {"move": ["KXHIGHNY", "KXBTCD"]}
        self.assertEqual((store.latest(wanted, t0 + 3600), store.keys("move")), ({}, []))
        self.assertTrue(store.record("move", "KXHIGHNY", started=t0, finished=t0 + 12.3451, payload=MOVE))
        self.assertEqual(store.latest(wanted, t0 + 12.345), {})  # computed a fraction of a millisecond later: not yet
        row = store.latest(wanted, t0 + 12.346)["move"]
        self.assertEqual(row, {"KXHIGHNY": {**MOVE, "t": "2026-09-22T12:00:12.346Z"}})  # KXBTCD: absent, never zero
        self.assertEqual(store.keys("move"), ["KXHIGHNY"])
        self.assertEqual(store.series(wanted, t0 - 3600, t0 + 12, 300), {})  # a tape ending before it never carries it
        tape = store.series(wanted, t0 - 3600, t0 + 3600, 300)["move"]
        self.assertEqual((list(tape), [r["t"] for r in tape["KXHIGHNY"]]), (["KXHIGHNY"], ["2026-09-22T12:00:12.346Z"]))

    def test_unchanged_move_content_is_stored_once_and_each_record_covers_three_cycles(self):
        store = self.recorder(None)
        t0 = self.clock()
        moved = {**MOVE, "markets": {"KXHIGHNY-26SEP22-B72.5": {"move_p5": 0.2, "move_p15": 0.3, "move_p60": 0.4}}}
        for offset, payload in ((0, MOVE), (300, MOVE), (600, MOVE), (900, moved)):
            store.record("move", "KXHIGHNY", started=t0 + offset - 60, finished=t0 + offset, payload=payload)
        row = store.coverage({"move": ["KXHIGHNY"]}, t0, t0 + 3600)["move"]["KXHIGHNY"]
        self.assertEqual((row["polls"], row["ok"], row["snapshots"], row["covered_seconds"]), (4, 4, 2, 1800.0))
        rows = store.series({"move": ["KXHIGHNY"]}, t0 - 1, t0 + 3600, 1)["move"]["KXHIGHNY"]
        self.assertEqual([(r["t"][11:19], r["markets"]["KXHIGHNY-26SEP22-B72.5"]["move_p15"]) for r in rows],
                         [("12:00:00", 0.2345), ("12:15:00", 0.3)])  # t: when that content was first computed
        self.assertEqual(store.latest({"move": ["KXHIGHNY"]}, t0 + 899)["move"]["KXHIGHNY"]["t"], "2026-09-22T12:00:00.000Z")

    def test_the_feeds_lane_never_polls_move_and_describe_lists_what_it_recorded(self):
        # Asked to "poll" move, the lane still plans nothing: an empty transport would fail any request.
        store = self.recorder({"move": ["KXHIGHNY"]}, transports=FakeTransport({}))
        store.record("move", "KXHIGHNY", started=self.clock() - 60, finished=self.clock(), payload=MOVE)
        self.assertEqual(store._plan(), [])
        self.assertFalse(store.due())
        self.clock.advance(3600)
        self.assertEqual({k: v for k, v in store.run().items() if k != "stored"}, {"polled": [], "failed": []})
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM polls WHERE feed = 'move'").fetchone()[0], 1)
        reader = FeedRecorder(path=store.path, clock=self.clock, niches={}, environ={}, allowed_hosts=())
        self.addCleanup(reader.close)
        self.assertEqual(reader.keys("move"), ["KXHIGHNY"])  # what the sensor recorded, not a poll plan
        self.assertNotIn("move", {feed for feed, _ in reader._plan()})
        described = reader.describe()["move"]
        self.assertEqual((described["keys"], described["recording"], described["host"]), (["KXHIGHNY"], ["KXHIGHNY"], ""))
        self.assertIn("not served", described["what"])
        self.assertIn("computed", described["point_in_time"])
        self.assertEqual(list(reader.coverage()["move"]), ["KXHIGHNY"])
        self.assertEqual(reader.health()["move"]["next_due"], None)


# ------------------------------------------------------------------ the backfilled history feeds
HOUR_MS = 3_600_000
DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&resolution=3600"
FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP"


def no_sleep(seconds):
    return None


def hours_of(query) -> set:
    """The candle opens (ms) a DVOL request's range names."""
    start, end = int(query["start_timestamp"]), int(query["end_timestamp"])
    return set(range(-(-start // HOUR_MS) * HOUR_MS, end + 1, HOUR_MS))


class Venues:
    """A Deribit and an OKX that answer from a synthetic history the way their docs say they page:
    Deribit the newest `cap` candles of the range asked (the one still open included) and a
    continuation when it cut the range short; OKX the newest `limit` settlements before `after`.
    Nothing before `since` exists, nothing after the clock, and OKX lists only `coins`."""

    def __init__(self, clock, since="2026-06-01T00:00:00Z", *, cap=1000, coins=("BTC", "ETH", "SOL"), interval_hours=8):
        self.clock, self.since_ms, self.cap, self.coins = clock, int(epoch(since) * 1000), cap, coins
        self.interval_ms = interval_hours * HOUR_MS
        self.served: list = []  # the candle opens each DVOL answer carried, in order

    @staticmethod
    def dvol(coin, open_ms):
        """The close of the DVOL candle that opens at `open_ms`."""
        return round((40.0 if coin == "BTC" else 60.0) + (open_ms // HOUR_MS % 97) * 0.13, 2)

    @staticmethod
    def rate(settled_ms):
        """The rate settled at `settled_ms`: two periods in five sit at OKX's 0.01% floor."""
        k = settled_ms // (8 * HOUR_MS) % 5
        return 0.0001 if k < 2 else round(0.0001 + (k - 1) * 0.00003, 8)

    def deribit(self, method, url, body):
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        coin, now_ms = query["currency"], int(self.clock() * 1000)
        first = -(-max(int(query["start_timestamp"]), self.since_ms) // HOUR_MS) * HOUR_MS
        opens = list(range(first, min(int(query["end_timestamp"]), now_ms) + 1, HOUR_MS))
        more = None
        if len(opens) > self.cap:
            opens = opens[-self.cap:]
            more = opens[0] - 1
        self.served.append(opens)
        data = [[t, self.dvol(coin, t - HOUR_MS), max(self.dvol(coin, t - HOUR_MS), self.dvol(coin, t)) + 0.2,
                 min(self.dvol(coin, t - HOUR_MS), self.dvol(coin, t)) - 0.2, self.dvol(coin, t)] for t in opens]
        return {"jsonrpc": "2.0", "result": {"data": data, "continuation": more}}

    def okx(self, method, url, body):
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        coin = query["instId"].split("-")[0]
        if coin not in self.coins:
            return {"code": "51001", "data": [], "msg": "Instrument ID does not exist"}
        top = int(self.clock() * 1000)
        if "after" in query:
            top = min(top, int(query["after"]) - 1)
        at, data = top // self.interval_ms * self.interval_ms, []
        while at >= self.since_ms and len(data) < min(int(query.get("limit") or 100), 100):
            data.append({"instId": query["instId"], "fundingRate": str(self.rate(at)), "realizedRate": str(self.rate(at)),
                         "fundingTime": str(at), "method": "current_period"})
            at -= self.interval_ms
        return {"code": "0", "data": data, "msg": ""}

    def routes(self) -> dict:
        return {derivs.DVOL: self.deribit, derivs.OKX_HISTORY: self.okx}

    def transport(self) -> FakeTransport:
        return FakeTransport(self.routes())


class HistoryCase(StoreCase):
    def setUp(self):
        super().setUp()
        self.clock.set("2026-09-22T12:34:56Z")
        self.venues = Venues(self.clock)

    def history(self, keys, transports=None, **kw):
        kw.setdefault("sleep", no_sleep)
        return self.recorder(keys, transports=transports if transports is not None else self.venues.transport(), **kw)

    def stamps(self, store, feed, key="BTC") -> list:
        return [at for (at,) in store.db.execute("SELECT received FROM snapshots WHERE feed = ? AND key = ? ORDER BY received", (feed, key))]


class HistoryFeeds(HistoryCase):
    def test_backfilled_rows_are_stamped_when_final_and_never_shown_before(self):
        store = self.history({"vol": ["BTC"], "funding": ["BTC"]}, backfill_pages=50)
        out = store.run()
        self.assertEqual(out["failed"], [])
        wanted = {"vol": ["BTC"], "funding": ["BTC"]}
        now = store.latest(wanted, self.clock())
        # At 12:34:56 the candle that opened at 12:00 is still open: the newest held closed at 12:00,
        # and it is the candle that OPENED at 11:00. The newest settlement is 08:00's.
        self.assertEqual((now["vol"]["BTC"]["t"], now["vol"]["BTC"]["close"], now["vol"]["BTC"]["hours"]),
                         ("2026-09-22T12:00:00.000Z", Venues.dvol("BTC", int(epoch("2026-09-22T11:00:00Z") * 1000)), 1))
        self.assertEqual((now["funding"]["BTC"]["t"], now["funding"]["BTC"]["rate"]),
                         ("2026-09-22T08:00:00.000Z", Venues.rate(int(epoch("2026-09-22T08:00:00Z") * 1000))))
        self.assertEqual(sorted(now["vol"]["BTC"]), ["change_24h", "close", "high", "hours", "low", "open", "t"])
        self.assertEqual(sorted(now["funding"]["BTC"]), ["avg_24h", "avg_7d", "interval_hours", "rate", "t", "zscore_30d"])
        self.assertLessEqual(max(self.stamps(store, "vol")), self.clock())  # a candle still open is never stored
        # Never shown before it became final: a millisecond before a close, the candle before it.
        self.assertEqual(store.latest(wanted, "2026-09-22T11:59:59.999Z")["vol"]["BTC"]["t"], "2026-09-22T11:00:00.000Z")
        self.assertEqual(store.latest(wanted, "2026-09-22T07:59:59.999Z")["funding"]["BTC"]["t"], "2026-09-22T00:00:00.000Z")
        # Every row is stamped at its close or its settlement, never with when it was fetched (kept as `started`).
        rows = store.db.execute("SELECT received, started FROM snapshots").fetchall()
        self.assertTrue(all(started >= received for received, started in rows))
        vol, funding = self.stamps(store, "vol"), self.stamps(store, "funding")
        self.assertTrue(all(at % 3600 == 0 for at in vol) and all(at % (8 * 3600) == 0 for at in funding))
        self.assertEqual([b - a for a, b in zip(vol, vol[1:])], [3600.0] * (len(vol) - 1))  # no hole
        # Two settlements at the same rate are two rows (the rate sits at OKX's floor for days), never one.
        rates = [Venues.rate(int(at * 1000)) for at in funding]
        self.assertTrue(any(a == b for a, b in zip(rates, rates[1:])))
        self.assertEqual([b - a for a, b in zip(funding, funding[1:])], [8 * 3600.0] * (len(funding) - 1))
        # The replay tape carries them by the same stamps, and a replay shows each from its t on.
        code = '''
from datetime import datetime

NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "t", "symbols": ["BTC/USD"], "bars": {"timeframe": "5Min", "limit": 5},
         "feeds": {"vol": ["BTC"], "funding": ["BTC"]}}
PARAMS = {}

def seconds(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()

def decide(ctx):
    feeds = ctx.get("feeds") or {}
    vol, funding = (feeds.get("vol") or {}).get("BTC"), (feeds.get("funding") or {}).get("BTC")
    for row in (vol, funding):
        if row is not None and seconds(row["t"]) > seconds(ctx["now"]):
            raise ValueError("a row from the future")
    seen = list((ctx.get("memory") or {}).get("seen") or [])
    seen.append([ctx["now"], vol and vol["t"], funding and funding["t"]])
    return {"intents": [], "memory": {"seen": seen}}
'''
        times = ["2026-09-21T23:59:59Z", "2026-09-22T00:00:00Z", "2026-09-22T00:30:00Z", "2026-09-22T07:59:59Z",
                 "2026-09-22T08:00:00Z", "2026-09-22T12:34:56Z"]
        tape = {"venue": "alpaca", "horizon": "hour", "step_seconds": 1,
                "steps": [{"t": t, "bars": {"BTC/USD": {"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}}} for t in times],
                "feeds": store.series(wanted, "2026-09-21T22:00:00Z", self.clock(), 1)}
        result = run_replay(code, {}, tape, stake=100.0, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["final_memory"]["seen"], [
            [times[0], "2026-09-21T23:00:00.000Z", "2026-09-21T16:00:00.000Z"],
            [times[1], "2026-09-22T00:00:00.000Z", "2026-09-22T00:00:00.000Z"],
            [times[2], "2026-09-22T00:00:00.000Z", "2026-09-22T00:00:00.000Z"],
            [times[3], "2026-09-22T07:00:00.000Z", "2026-09-22T00:00:00.000Z"],
            [times[4], "2026-09-22T08:00:00.000Z", "2026-09-22T08:00:00.000Z"],
            [times[5], "2026-09-22T12:00:00.000Z", "2026-09-22T08:00:00.000Z"]])

    def test_the_backfill_reaches_its_target_and_resumes_without_fetching_a_page_twice(self):
        venues = Venues(self.clock, cap=100)  # Deribit's pages cut short: every range pages on a continuation
        fake = venues.transport()
        wanted = {"vol": ["BTC"], "funding": ["BTC"]}
        store = self.history(wanted, transports=fake, backfill_pages=3)
        store.run()  # the newest page of each, then three pages of backfill
        first = store.coverage(wanted)
        self.assertFalse(first["vol"]["BTC"]["backfill"]["complete"])
        self.assertEqual(first["vol"]["BTC"]["backfill"]["pages"], 3)
        held = min(self.stamps(store, "vol"))
        asked = len(fake.calls)
        store.close()
        # A restart -- a new release builds a new recorder over the same store -- goes on from the
        # oldest row held: its first backfill request asks for nothing at or after it.
        again = self.history(wanted, transports=fake, backfill_pages=3)
        self.assertEqual(again.coverage(wanted)["vol"]["BTC"]["backfill"]["pages"], 3)  # read back from `backfills`
        again.run()
        tail = [c["query"] for c in fake.calls[asked:] if "currency" in c["query"] and hours_of(c["query"]) and max(hours_of(c["query"])) < held * 1000]
        self.assertTrue(tail)
        self.assertLess(max(hours_of(tail[0])), held * 1000 - HOUR_MS)  # not even the oldest candle held (it opened an hour before)
        for _ in range(40):
            if not again._backfill_pending():
                break
            self.clock.advance(61)
            again.run()
        self.assertFalse(again._backfill_pending())
        # Every candle older than the first page came back from the venue exactly once, restart or not.
        first = min(venues.served[0])
        older = [hour for page in venues.served for hour in page if hour < first]
        self.assertGreater(len(older), 1000)
        self.assertEqual(len(older), len(set(older)))
        # OKX's pages go back by `after`, each from the oldest settlement held, never the same twice.
        afters = [int(c["query"]["after"]) for c in fake.calls if "instId" in c["query"] and "after" in c["query"]]
        self.assertGreaterEqual(len(afters), 2)
        self.assertEqual(afters, sorted(set(afters), reverse=True))
        # Both reached their targets -- 60 days and the lookback of their derived fields (a day, 30
        # days) before the first pass -- with no hole, and say where they came from.
        state = again.coverage(wanted)
        began = epoch("2026-09-22T12:34:56Z")
        for feed, step, days in (("vol", 3600.0, 61), ("funding", 8 * 3600.0, 90)):
            row = state[feed]["BTC"]["backfill"]
            stamps = self.stamps(again, feed)
            self.assertTrue(row["complete"] and not row["exhausted"], row)
            self.assertEqual((row["source"], row["rows"], row["since"], row["target"]),
                             (DVOL_URL if feed == "vol" else FUNDING_URL, len(stamps), feeds.stamp(stamps[0]), feeds.stamp(began - days * 86400)))
            self.assertTrue(0 <= stamps[0] - (began - days * 86400) < step)  # the first row at or after the target
            self.assertEqual({b - a for a, b in zip(stamps, stamps[1:])}, {step})
        self.assertEqual(again.db.execute("SELECT COUNT(*) FROM backfills WHERE done = 1").fetchone()[0], 2)

    def test_a_venue_with_nothing_older_ends_the_backfill_there(self):
        young = Venues(self.clock, since="2026-09-01T00:00:00Z")  # a coin listed three weeks ago
        store = self.history({"vol": ["BTC"], "funding": ["BTC"]}, transports=young.transport(), backfill_pages=50)
        store.run()
        state = store.coverage({"vol": ["BTC"], "funding": ["BTC"]})
        for feed in ("vol", "funding"):
            self.assertTrue(state[feed]["BTC"]["backfill"]["complete"])
            self.assertTrue(state[feed]["BTC"]["backfill"]["exhausted"])
        self.assertEqual(state["vol"]["BTC"]["first_ok"], "2026-09-01T01:00:00.000Z")  # the first candle's close
        self.assertEqual(state["funding"]["BTC"]["first_ok"], "2026-09-01T00:00:00.000Z")
        self.assertFalse(store._backfill_pending())
        calls = len(store._fetcher("vol").transport.calls)
        self.clock.advance(120)
        store.run()
        self.assertEqual(len(store._fetcher("vol").transport.calls), calls)  # an exhausted venue is not asked again

    def test_derived_fields_read_only_rows_at_or_before_their_own(self):
        store = self.history({"vol": ["BTC"], "funding": ["BTC", "SOL"]})
        t0 = epoch("2026-08-01T00:00:00Z")
        closes = [50.0 + (i * 7 % 11) for i in range(72)]
        store._store_history("vol", "BTC", [(t0 + 3600 * (i + 1), {"open": c, "high": c, "low": c, "close": c, "hours": 1})
                                            for i, c in enumerate(closes)], fetched=self.clock())
        wanted = {"vol": ["BTC"]}
        view = store.series(wanted, t0, t0 + 72 * 3600, 3600)["vol"]["BTC"]
        self.assertEqual(len(view), 72)
        self.assertEqual([row["change_24h"] for row in view[:24]], [None] * 24)  # nothing held 24 hours before
        self.assertEqual([row["change_24h"] for row in view[24:27]],
                         [round(closes[24] - closes[0], 6), round(closes[25] - closes[1], 6), round(closes[26] - closes[2], 6)])
        self.assertEqual(store.latest(wanted, t0 + 30 * 3600)["vol"]["BTC"], view[29])
        # A later row, however extreme, changes nothing before it.
        store._store_history("vol", "BTC", [(t0 + 73 * 3600, {"open": 999.0, "high": 999.0, "low": 999.0, "close": 999.0, "hours": 1})],
                             fetched=self.clock())
        self.assertEqual(store.series(wanted, t0, t0 + 73 * 3600, 3600)["vol"]["BTC"][:72], view)
        # Funding every eight hours for 40 days: each field reads its own window of rows at or before it.
        rates = [0.0001 * (1 + (i * 5 % 9) / 10) for i in range(120)]
        settle = [t0 + 8 * 3600 * i for i in range(120)]
        store._store_history("funding", "BTC", [(at, {"rate": r}) for at, r in zip(settle, rates)], fetched=self.clock())
        rows = store.series({"funding": ["BTC"]}, t0 - 1, settle[-1], 3600)["funding"]["BTC"]
        self.assertEqual(len(rows), 120)
        self.assertEqual({row["interval_hours"] for row in rows}, {8})
        mean = lambda xs: round(sum(xs) / len(xs), 10)  # noqa: E731
        self.assertEqual([row["avg_24h"] for row in rows[:3]], [None] * 3)  # the history does not reach back a day
        self.assertEqual(rows[3]["avg_24h"], mean(rates[1:4]))
        self.assertEqual([row["avg_7d"] for row in rows[:21]], [None] * 21)
        self.assertEqual(rows[21]["avg_7d"], mean(rates[1:22]))
        self.assertEqual([row["zscore_30d"] for row in rows[:90]], [None] * 90)
        self.assertEqual(rows[100]["zscore_30d"], zscore(rates[100], rates[10:100]))
        self.assertEqual(rows[100]["avg_24h"], mean(rates[98:101]))
        self.assertEqual(store.latest({"funding": ["BTC"]}, settle[100] + 1)["funding"]["BTC"], rows[100])
        store._store_history("funding", "BTC", [(settle[-1] + 8 * 3600, {"rate": 0.05})], fetched=self.clock())
        self.assertEqual(store.series({"funding": ["BTC"]}, t0 - 1, settle[-1] + 8 * 3600, 3600)["funding"]["BTC"][:120], rows)
        # A coin that settles every four hours says so.
        store._store_history("funding", "SOL", [(t0 + 4 * 3600 * i, {"rate": 0.0001}) for i in range(5)], fetched=self.clock())
        self.assertEqual([row["interval_hours"] for row in store.series({"funding": ["SOL"]}, t0 - 1, t0 + 86400, 60)["funding"]["SOL"]],
                         [8, 4, 4, 4, 4])

    def test_a_venue_that_is_down_is_a_failed_poll_and_a_warning_at_most_hourly(self):
        down = FakeTransport(default=TransportError("the host is down"))
        store = self.history({"vol": ["BTC", "ETH"], "funding": ["BTC"]}, transports=down)
        out = store.run()
        self.assertEqual(sorted({(feed, key) for feed, key, _ in out["failed"]}), [("funding", "BTC"), ("vol", "BTC"), ("vol", "ETH")])
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)  # nothing fabricated
        self.assertEqual(store.db.execute("SELECT COUNT(*), SUM(ok) FROM polls").fetchone(), (5, 0))  # three polls, two pages
        self.assertEqual(store.latest({"vol": ["BTC"], "funding": ["BTC"]}, self.clock()), {})
        self.assertEqual(sorted(text.split(" polls failed")[0].rsplit(" ", 1)[1] for _, text in self.alerts), ["funding", "vol"])
        self.assertIn("feeds: 2 of 2 vol polls failed", " ".join(text for _, text in self.alerts))  # one warning a feed
        row = store.coverage({"vol": ["BTC"]})["vol"]["BTC"]
        self.assertIsNone(row["first_ok"])
        self.assertIn("the host is down", row["last_error"])
        self.assertTrue(row["backfill"]["pending"])  # a replay that needs it waits; it is not missing data
        self.clock.advance(61)
        self.assertFalse(store.due())  # a venue that failed is not asked again every minute, backfill included
        self.clock.advance(240)
        self.assertTrue(store.due())  # but in five minutes, not at the next hour
        store.run()
        self.assertEqual(len(self.alerts), 2)  # not again within the hour
        self.clock.advance(3600)
        store.run()
        self.assertEqual(len(self.alerts), 4)
        self.assertTrue(all(level == "warning" for level, _ in self.alerts))  # never "error": that rolls a release back
        # When the venue answers again, the history comes in as if nothing had happened.
        store._fetchers.clear()
        store._transports = self.venues.transport()
        self.clock.advance(3600)
        self.assertEqual(store.run()["failed"], [])
        self.assertEqual(store.latest({"vol": ["BTC"]}, self.clock())["vol"]["BTC"]["t"], "2026-09-22T14:00:00.000Z")

    def test_a_coin_okx_does_not_list_is_unavailable_and_asked_again_hours_later(self):
        fake = self.venues.transport()
        store = self.history({"funding": ["BTC", "DOGE"]}, transports=fake, backfill_pages=50)
        out = store.run()
        self.assertEqual([(feed, key) for feed, key, _ in out["failed"]], [("funding", "DOGE")])
        self.assertIn("okx code 51001", out["failed"][0][2])
        entry = store.coverage({"funding": ["DOGE"]})["funding"]["DOGE"]
        self.assertIsNone(entry["first_ok"])
        self.assertFalse(entry["backfill"]["pending"])  # unavailable, not waiting: never guessed, never a zero row
        self.assertFalse(store._backfill_pending())
        doge = lambda: sum(1 for call in fake.calls if call["query"].get("instId") == "DOGE-USDT-SWAP")  # noqa: E731
        asked = doge()
        self.clock.advance(1800)
        self.assertEqual(store.run()["failed"], [])
        self.assertEqual(doge(), asked)
        self.clock.advance(6 * 3600)
        store.run()
        self.assertEqual(doge(), asked + 1)

    def test_live_polls_follow_the_hour_and_an_outage_leaves_no_hole(self):
        store = self.history({"vol": ["BTC"], "funding": ["BTC"]}, backfill_pages=50)
        store.run()
        health = store.health()
        self.assertEqual((health["vol"]["next_due"], health["funding"]["next_due"]), ("2026-09-22T13:01:30.000Z", "2026-09-22T13:01:30.000Z"))
        self.assertEqual(health["vol"]["backfill"], {"complete": 1, "in_progress": [], "unlisted": []})
        self.clock.set("2026-09-22T13:01:29Z")
        self.assertFalse(store.due())
        self.clock.set("2026-09-22T13:01:30Z")
        self.assertTrue(store.due())
        self.assertEqual(store.run()["polled"], ["vol", "funding"])
        self.assertEqual(store.latest({"vol": ["BTC"]}, self.clock())["vol"]["BTC"]["t"], "2026-09-22T13:00:00.000Z")
        self.assertEqual(store.health()["funding"]["next_due"], "2026-09-22T13:31:30.000Z")
        # Down three days: the next pass pages back to the newest row held, so the history has no hole.
        self.clock.set("2026-09-25T13:05:00Z")
        store.run()
        vol, funding = self.stamps(store, "vol"), self.stamps(store, "funding")
        self.assertEqual((feeds.stamp(vol[-1]), feeds.stamp(funding[-1])), ("2026-09-25T13:00:00.000Z", "2026-09-25T08:00:00.000Z"))
        self.assertEqual({b - a for a, b in zip(vol, vol[1:])}, {3600.0})
        self.assertEqual({b - a for a, b in zip(funding, funding[1:])}, {8 * 3600.0})

    def test_a_backfill_pass_gives_way_when_a_live_poll_falls_due(self):
        venues = Venues(self.clock, cap=100)
        fake = FakeTransport({**venues.routes(), **{key: value for key, value in transport().routes.items() if key != derivs.DVOL}})
        # Each pause between pages is 200 seconds of the House's clock: the perps poll falls due
        # (every 300 seconds) during the second, and the pass stops there.
        store = self.recorder({"perps": ["BTC"], "vol": ["BTC"]}, transports=fake, sleep=lambda seconds: self.clock.advance(200),
                              backfill_pages=50)
        out = store.run()
        self.assertEqual(out["polled"], ["perps", "vol", "backfill:vol:BTC", "backfill:vol:BTC"])
        self.assertTrue(store.due())
        self.assertEqual(store.run()["polled"][:2], ["perps", "backfill:vol:BTC"])  # the live poll first, then on from there

    def test_coverage_counts_the_backfilled_span_and_says_where_it_came_from(self):
        store = self.history({"vol": ["BTC"], "funding": ["BTC"]}, backfill_pages=50)
        store.run()
        now = self.clock()
        window = store.coverage({"vol": ["BTC"], "funding": ["BTC"]}, now - 49 * 86400, now)
        self.assertEqual((window["vol"]["BTC"]["covered_seconds"], window["funding"]["BTC"]["covered_seconds"]), (49 * 86400.0, 49 * 86400.0))
        self.assertEqual(window["vol"]["BTC"]["backfill"]["source"], DVOL_URL)
        self.assertEqual(window["funding"]["BTC"]["backfill"]["source"], FUNDING_URL)
        # A hole in the rows is not covered: the rows are the record, not the polls.
        store.db.execute("DELETE FROM snapshots WHERE feed = 'vol' AND received > ? AND received < ?", (now - 10 * 86400, now - 9 * 86400))
        store.db.commit()
        self.assertEqual(store.coverage({"vol": ["BTC"]}, now - 49 * 86400, now)["vol"]["BTC"]["covered_seconds"],
                         49 * 86400.0 - 86400.0 + 2 * 3600.0 - 3600.0)
        rows = {e.payload["feed"]: e.payload for e in self.ledger.iter(kinds="data.coverage")}
        self.assertEqual(sorted(rows), ["funding", "vol"])
        self.assertEqual((rows["vol"]["status"], rows["vol"]["backfill"]["BTC"]["source"]), ("current", DVOL_URL))
        self.assertIn("stamped at its close", rows["vol"]["point_in_time"])

    def test_needs_feeds_accept_vol_and_funding_known_keys_only(self):
        self.assertEqual(requested({"vol": ["btc", "XBT", "ETH-USD", "SOL", "BTCDVOL", "eth"], "funding": ["btc/usd", "PEPE", "sol", "XBT"]}),
                         {"vol": ["BTC", "ETH"], "funding": ["BTC", "SOL"]})
        self.assertEqual(len(requested({"funding": sorted(feeds.known_perps())})["funding"]), 6)
        self.assertEqual(requested({"vol": ["DOGE"]}), {})  # no DVOL but BTC's and ETH's
        strikes = niches.load()["kalshi-crypto-strikes"]
        out = niches.constrain({"venue": "kalshi", "horizon": "hour", "series": ["KXBTCD"],
                                "feeds": {"vol": ["BTC", "SOL"], "funding": ["btc", "hype"], "perps": ["BTC"]}}, strikes)
        self.assertEqual(out["feeds"], {"vol": ["BTC"], "funding": ["BTC", "HYPE"], "perps": ["BTC"]})
        self.assertEqual({name: request_feed(name) for name in (
            "deribit_dvol", "btc_implied_volatility", "okx_funding_rate_history", "historical_funding_rates", "settled_funding_rates",
            "perp_funding_rates", "equity_implied_volatility_surface", "historical_scores", "kalshi_open_interest_history")},
            {"deribit_dvol": "vol", "btc_implied_volatility": "vol", "okx_funding_rate_history": "funding",
             "historical_funding_rates": "funding", "settled_funding_rates": "funding", "perp_funding_rates": "perps",
             "equity_implied_volatility_surface": None, "historical_scores": None, "kalshi_open_interest_history": None})

    def test_requests_for_the_history_are_answered_once_it_is_held(self):
        commons = Commons(self.ledger, clock=self.clock)
        why = "the strategy prices strikes against implied vol and funding extremes"
        ids = {name: commons.request_tool("carry-1", name, why)["queued"] for name in ("deribit_dvol_history", "okx_funding_rate_history")}
        store = self.history({"vol": ["BTC"], "funding": ["BTC"]}, backfill_pages=50)
        self.assertEqual(store.fulfil_requests(commons), [])
        store.run()
        self.assertEqual(sorted(store.fulfil_requests(commons)), sorted(ids.values()))
        answers = [e.payload["outcome"] for e in self.ledger.iter(kinds="tool.fulfilled")]
        self.assertTrue(any("ctx['feeds']['vol']" in text and "replayed at once" in text for text in answers))
        self.assertTrue(any("ctx['feeds']['funding']" in text and "zscore_30d" in text for text in answers))


# ------------------------------------------------------------------------------ in the House
FEED_READER = '''
from datetime import datetime

NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "feed-reader", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5, "feeds": {"perps": ["btc"]}}
PARAMS = {}


def seconds(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def decide(ctx):
    memory = dict(ctx.get("memory") or {})
    row = ((ctx.get("feeds") or {}).get("perps") or {}).get("BTC")
    if row is not None:
        if seconds(row["t"]) > seconds(ctx["now"]):
            raise ValueError("a feed row from the future")
        memory["seen"] = int(memory.get("seen") or 0) + 1
        pairs = list(memory.get("pairs") or [])
        if len(pairs) < 12 and (not pairs or pairs[-1][1] != row["t"]):
            pairs.append([ctx["now"], row["t"], row["okx"]["rate"]])
        memory["pairs"] = pairs
    return {"intents": [], "memory": memory}
'''


VOL_READER = '''
from datetime import datetime

NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "vol-reader", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5, "feeds": {"vol": ["btc"]}}
PARAMS = {}


def seconds(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def decide(ctx):
    memory = dict(ctx.get("memory") or {})
    row = ((ctx.get("feeds") or {}).get("vol") or {}).get("BTC")
    if row is not None:
        now = seconds(ctx["now"])
        if seconds(row["t"]) > now:
            raise ValueError("a candle from the future")
        if now - seconds(row["t"]) >= 3600:
            raise ValueError("not the newest closed candle")
        memory["seen"] = int(memory.get("seen") or 0) + 1
        pairs = list(memory.get("pairs") or [])
        if len(pairs) < 3 and (not pairs or pairs[-1][1] != row["t"]):
            pairs.append([ctx["now"], row["t"], row["close"], row["change_24h"]])
        memory["pairs"] = pairs
    return {"intents": [], "memory": memory}
'''


class InTheHouse(HouseCase):
    def attach(self, keys, transports=None, **kw) -> FeedRecorder:
        recorder = FeedRecorder(self.house, Path(self.dir.name) / "feeds.sqlite", transports, keys=keys, **kw)
        self.house.feeds = recorder
        self.addCleanup(recorder.close)  # also when a test takes it off the House
        return recorder

    def test_a_strategy_declaring_vol_replays_as_soon_as_the_backfill_covers_its_window(self):
        self.clock.now = epoch("2026-09-12T12:00:00Z")
        recorder = self.attach({"vol": ["BTC"]}, transports=Venues(self.clock).transport(), sleep=no_sleep)
        agent = self.house.spawn("reader", "test-family", VOL_READER, reason="test")
        self.assertEqual(agent.needs["feeds"], {"vol": ["BTC"]})
        # Before the first pass nothing is held and the backfill is due: unsupported input, and a
        # wait -- not a trial, and not a line blocked on missing data.
        with self.assertRaises(ValueError) as caught:
            self.house._run_replay(agent, agent.code, agent.needs, agent.params)
        self.assertTrue(str(caught.exception).startswith("unsupported input: feeds being backfilled: vol BTC"), str(caught.exception))
        self.assertEqual(self.house._replay_own(agent), {"agent": agent.id, "skipped": "waiting for recorded feeds"})
        texts = [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert")]
        self.assertFalse(any("replay could not run" in text for text in texts))
        self.assertEqual((self.house.ledger.count(kinds="experiment.started"), self.house.ledger.count(kinds="eval.trial")), (0, 0))
        # One pass -- the newest page, then the backfill -- and the replay runs: no twenty hours of recording to wait for.
        self.assertEqual(recorder.run()["failed"], [])
        key, tape = self.house.tape_for(agent.needs)
        self.assertTrue(key.startswith("alpaca:") and key.endswith(':feeds:{"vol":["BTC"]}:ready'), key)
        window = tape["feeds_coverage"]["vol"]["BTC"]
        self.assertEqual(window["covered_seconds"], 21 * 86400.0)  # the whole live window of an hourly Alpaca strategy
        self.assertTrue(window["backfill"]["complete"])
        # The House's longest window of an hourly or Kalshi daily strategy is 49 days: 60 days back
        # (49 and a week, at least 60), and a day more for change_24h.
        self.assertEqual(recorder.backfill_days(), 60.0)
        self.assertEqual(window["backfill"]["since"], "2026-07-13T12:00:00.000Z")
        result = run_replay(agent.code, {}, tape, stake=200.0, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["errors"], 0)  # never a candle from the future, always the newest closed one
        memory = result["final_memory"]
        self.assertEqual(memory["seen"], len(tape["steps"]))
        opened = int(epoch("2026-09-09T23:00:00Z") * 1000)
        self.assertEqual(memory["pairs"][0], ["2026-09-10T00:00:00Z", "2026-09-10T00:00:00.000Z", Venues.dvol("BTC", opened),
                                              round(Venues.dvol("BTC", opened) - Venues.dvol("BTC", opened - 24 * HOUR_MS), 6)])
        run, _ = self.house._run_replay(agent, agent.code, agent.needs, agent.params)
        self.assertTrue(run["ok"], run)
        self.assertEqual(self.house.ledger.count(kinds="experiment.started"), 1)
        # A House whose store holds no vol and does not poll it: missing data, which is not a wait.
        other = FeedRecorder(self.house, Path(self.dir.name) / "other.sqlite", keys={"perps": ["BTC"]})
        self.addCleanup(other.close)
        self.house.feeds = other
        with self.assertRaises(ValueError) as caught:
            self.house._run_replay(agent, agent.code, agent.needs, agent.params)
        self.assertTrue(str(caught.exception).startswith("unsupported input: feeds not recorded: vol BTC"), str(caught.exception))

    def test_research_and_the_foundry_are_told_the_history_is_replayable_now(self):
        from league.hypotheses import REPLAY_VIEW

        self.clock.now = epoch("2026-09-12T12:00:00Z")
        recorder = self.attach({"vol": ["BTC", "ETH"], "funding": ["BTC"]}, transports=Venues(self.clock).transport(), sleep=no_sleep)
        agent = self.seated()
        before = self.house.research_capabilities(agent)["observations"]
        self.assertEqual((before["feeds"]["vol"]["backfill_in_progress"], before["feeds"]["vol"]["replayable_now"]),
                         (["BTC", "ETH"], {"hour": [], "day": []}))
        self.assertNotIn("replayable_history", before)
        recorder.run()
        observed = self.house.research_capabilities(agent)["observations"]
        vol, funding = observed["feeds"]["vol"], observed["feeds"]["funding"]
        self.assertEqual((vol["backfill_complete"], vol["backfill_in_progress"]), (["BTC", "ETH"], []))
        self.assertEqual(vol["backfilled_since"], {"BTC": "2026-07-13T12:00:00.000Z", "ETH": "2026-07-13T12:00:00.000Z"})
        self.assertEqual((vol["recording_since"], funding["backfilled_since"]), ("2026-07-13T12:00:00.000Z", {"BTC": "2026-06-14T16:00:00.000Z"}))
        self.assertEqual(vol["replayable_now"], {"hour": ["BTC", "ETH"], "day": ["BTC", "ETH"]})
        self.assertEqual(funding["replayable_now"], {"hour": ["BTC"], "day": ["BTC"]})
        self.assertIn("stamped at its close", vol["point_in_time"])
        self.assertIn("replayed at once", observed["feeds"]["replay"])
        self.assertEqual(observed["replayable_history"]["funding"]["replayable_now"], {"hour": ["BTC"], "day": ["BTC"]})
        # replay_coverage for a candidate that reads them says a replay may use them now, and from where they came.
        needs = {**agent.needs, "feeds": {"vol": ["BTC"], "funding": ["BTC"]}}
        coverage = self.house.research_coverage(agent, needs)
        self.assertTrue(coverage["feeds"]["replay_ready"], coverage)
        self.assertEqual(coverage["feeds"]["coverage"]["vol"]["BTC"]["backfill"]["source"], DVOL_URL)
        self.assertEqual(coverage["feeds"]["coverage"]["funding"]["BTC"]["backfill"]["source"], FUNDING_URL)
        self.assertIn("backfilled over the replay window", coverage["feeds"]["note"])
        # And the foundry's packet carries what a replay step sees of them.
        self.assertIn("replayable now", REPLAY_VIEW["feeds"])

    def history(self, recorder, first: str, last: str, every: float = 300.0, offset: float = 137.4) -> list[float]:
        """Successful BTC polls from `first` to `last`, received `offset` seconds into each interval."""
        at, stop, received = epoch(first) + offset, epoch(last), []
        while at <= stop:
            recorder.record("perps", "BTC", started=at - 2, finished=at, payload=perp_row(round(at % 100000, 3)))
            received.append(at)
            at += every
        return received

    def test_a_strategy_declaring_move_waits_for_recorded_blocks_like_any_live_feed(self):
        recorder = self.attach(None)
        wanted = {"move": ["KXHIGHNY"]}
        needs = {"venue": "kalshi", "horizon": "hour", "series": ["KXHIGHNY"], "feeds": wanted}

        def shortfall():
            start, end = self.house._live_window(needs)
            return self.house._feeds_shortfall(needs, wanted, recorder.coverage(wanted, start, end))

        self.clock.now = epoch("2026-09-12T12:00:00Z")
        self.assertTrue(shortfall().startswith("unsupported input: feeds not recorded: move KXHIGHNY; the House records move nothing"))
        at = epoch("2026-09-12T09:00:00Z")
        while at <= epoch("2026-09-13T08:00:00Z"):  # a record every 5-minute cycle, never back-filled
            recorder.record("move", "KXHIGHNY", started=at - 60, finished=at, payload={**MOVE, "n": int(at) % 7})
            if at == epoch("2026-09-12T12:00:00Z"):
                self.assertTrue(shortfall().startswith(f"{feeds.WAITING} 2026-09-12T09:00:00.000Z"), shortfall())
                self.assertIn("needs 20 hour blocks of them and has 3.0", shortfall())
            at += 300
        self.clock.now = epoch("2026-09-13T08:00:00Z")
        self.assertEqual(shortfall(), "")  # 23 hours recorded: a replay may use it, each row from its t

    def test_ctx_feeds_appears_only_when_declared(self):
        recorder = self.attach({"perps": ["BTC", "ETH"], "sports": ["nfl"]})
        recorder.record("perps", "BTC", started=self.clock() - 2, finished=self.clock() - 1, payload=perp_row(0.0003))
        both = FEED_READER.replace('"feeds": {"perps": ["btc"]}', '"feeds": {"perps": ["btc", "ETH"], "sports": ["NFL"]}')
        reader = self.seated(name="reader", code=both)
        self.assertEqual(reader.needs["feeds"], {"perps": ["BTC", "ETH"], "sports": ["nfl"]})
        ctx = self.house.snapshot(reader, self.house.book_of(reader))
        self.assertEqual(list(ctx["feeds"]), ["perps"])  # nothing recorded for nfl or ETH: absent, not zero
        self.assertEqual((sorted(ctx["feeds"]["perps"]), ctx["feeds"]["perps"]["BTC"]["okx"]["rate"]), (["BTC"], 0.0003))
        plain = self.seated(name="plain", code=BUYER)
        self.assertNotIn("feeds", self.house.snapshot(plain, self.house.book_of(plain)))
        self.house.feeds = None
        self.house._data_cache.clear()
        self.assertNotIn("feeds", self.house.snapshot(reader, self.house.book_of(reader)))  # a House without the recorder

    def test_a_replay_before_the_feeds_span_the_gate_is_unsupported_and_no_trial(self):
        recorder = self.attach({"perps": ["BTC"]})
        self.clock.now = epoch("2026-09-12T12:00:00Z")
        self.history(recorder, "2026-09-12T09:00:00Z", "2026-09-12T11:55:00Z")  # three hours of an hourly strategy's twenty
        agent = self.house.spawn("reader", "test-family", FEED_READER, reason="test")
        self.assertEqual(agent.needs["feeds"], {"perps": ["BTC"]})
        with self.assertRaises(ValueError) as caught:
            self.house._run_replay(agent, agent.code, agent.needs, agent.params)
        self.assertTrue(str(caught.exception).startswith("unsupported input: feeds recorded live since 2026-09-12T09:02:17.400Z"),
                        str(caught.exception))
        self.assertIn("needs 20 hour blocks", str(caught.exception))
        self.assertEqual(self.house.ledger.count(kinds="experiment.started"), 0)  # refused before any tape was built
        self.assertEqual(self.house._replay_own(agent), {"agent": agent.id, "skipped": "waiting for recorded feeds"})
        self.house._replay_own(agent)
        texts = [(e.payload["level"], e.payload["text"]) for e in self.house.ledger.iter(kinds="ops.alert")]
        self.assertEqual([level for level, text in texts if "waits for recorded feeds" in text], ["info"])  # once a day
        self.assertFalse(any("replay could not run" in text for _, text in texts))  # not a line blocked on missing data
        self.assertEqual(self.house.ledger.count(kinds="eval.trial"), 0)
        coverage = self.house.research_coverage(agent)
        self.assertFalse(coverage["feeds"]["replay_ready"])
        self.assertIn("recorded live since", coverage["feeds"]["blocked_by"])
        # A key the House does not record is missing data, not a wait; and a House with no recorder replays no feeds.
        with self.assertRaises(ValueError) as caught:
            self.house._run_replay(agent, agent.code, {**agent.needs, "feeds": {"perps": ["ETH"]}}, agent.params)
        self.assertTrue(str(caught.exception).startswith("unsupported input: feeds not recorded: perps ETH"))
        self.house.feeds = None
        with self.assertRaises(ValueError) as caught:
            self.house._run_replay(agent, agent.code, agent.needs, agent.params)
        self.assertIn("records no live feeds", str(caught.exception))
        self.assertEqual(self.house.ledger.count(kinds="eval.trial"), 0)

    def test_with_enough_recorded_history_the_replay_sees_each_row_only_from_its_receive_time(self):
        recorder = self.attach({"perps": ["BTC"]})
        self.clock.now = epoch("2026-09-12T12:00:00Z")
        received = self.history(recorder, "2026-09-10T02:00:00Z", "2026-09-12T11:55:00Z")  # about 58 hours
        agent = self.house.spawn("reader", "test-family", FEED_READER, reason="test")
        key, tape = self.house.tape_for(agent.needs)
        self.assertTrue(key.startswith("alpaca:") and key.endswith(':feeds:{"perps":["BTC"]}:ready'), key)  # never the deep store
        self.assertEqual(len(tape["feeds"]["perps"]["BTC"]), len(received))
        result = run_replay(agent.code, {}, tape, stake=200.0, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["errors"], 0)  # the strategy raises on any row from its future
        memory = result["final_memory"]
        # The fake tape steps every five minutes from 2026-09-10T00:00; the first row, received at
        # 02:02:17.4, is seen first at 02:05 and never before, and each step sees the latest row.
        self.assertEqual(memory["pairs"][:3], [["2026-09-10T02:05:00Z", "2026-09-10T02:02:17.400Z", round(received[0] % 100000, 3)],
                                               ["2026-09-10T02:10:00Z", "2026-09-10T02:07:17.400Z", round(received[1] % 100000, 3)],
                                               ["2026-09-10T02:15:00Z", "2026-09-10T02:12:17.400Z", round(received[2] % 100000, 3)]])
        steps_after_first = sum(1 for step in tape["steps"] if epoch(step["t"]) >= received[0])
        self.assertEqual(memory["seen"], steps_after_first)
        # And the House's own path: the feeds span the gate, so the replay runs, as an experiment.
        run, _ = self.house._run_replay(agent, agent.code, agent.needs, agent.params)
        self.assertTrue(run["ok"], run)
        self.assertEqual(run["errors"], 0)
        self.assertEqual(self.house.ledger.count(kinds="experiment.started"), 1)

    def test_a_tape_built_before_the_feeds_spanned_the_gate_is_not_reused_once_they_do(self):
        recorder = self.attach({"perps": ["BTC"]})
        self.clock.now = epoch("2026-09-11T00:00:00Z")
        self.history(recorder, "2026-09-10T20:00:00Z", "2026-09-10T23:55:00Z")
        agent = self.house.spawn("reader", "test-family", FEED_READER, reason="test")
        short, _ = self.house.tape_for(agent.needs)
        self.assertTrue(short.endswith(":short"))
        self.history(recorder, "2026-09-11T00:00:00Z", "2026-09-11T19:55:00Z")
        self.clock.now = epoch("2026-09-11T20:00:00Z")
        ready, tape = self.house.tape_for(agent.needs)
        self.assertTrue(ready.endswith(":ready"))
        self.assertGreaterEqual(min(row["covered_seconds"] for row in tape["feeds_coverage"]["perps"].values()), 20 * 3600)

    def test_the_kalshi_tape_carries_the_feeds_and_its_key_names_them(self):
        recorder = self.attach({"sports": ["nfl"]})
        recorder.record("sports", "nfl", started=self.clock() - 60, finished=self.clock() - 59,
                        payload={"league": "nfl", "espn": "football/nfl", "events": []})

        class Kalshi:
            def tape(self, series, **kw):
                return {"venue": "kalshi", "horizon": kw["horizon"], "step_seconds": kw["step_seconds"], "steps": [], "results": {}}

        self.house.kalshi_data = Kalshi()
        needs = niches.constrain({"venue": "kalshi", "horizon": "day", "style": "g", "series": ["KXNFLGAME"],
                                  "feeds": {"sports": ["KXNFLGAME", "EPL"]}}, niches.load()["kalshi-sports"])
        key, tape = self.house.tape_for(needs)
        self.assertTrue(key.startswith("kalshi:") and key.endswith(':feeds:{"sports":["nfl","epl"]}:short'), key)
        self.assertEqual(tape["step_seconds"], 1800)
        self.assertEqual(list(tape["feeds"]["sports"]), ["nfl"])  # epl has recorded nothing: absent
        self.assertIsNone(tape["feeds_coverage"]["sports"]["epl"]["first_ok"])

    def test_tick_starts_the_feed_job_even_while_paused_and_answers_the_requests(self):
        recorder = self.attach({"sports": ["nfl"], "perps": ["BTC"]}, transports=transport())
        asked = self.house.commons.request_tool("carry-1", "live_sports_scores", "the games my contracts settle on, while they are played")
        (self.house.root / "PAUSE").write_text("maintenance", encoding="utf-8")
        summary = self.house.tick()
        self.house.wait(10)
        self.assertEqual(summary["paused"], "maintenance")
        recorded = recorder.coverage()
        self.assertEqual((recorded["sports"]["nfl"]["ok"], recorded["perps"]["BTC"]["ok"]), (1, 1))
        jobs = [e.payload["state"] for e in self.house.ledger.iter(kinds="ops.job") if e.payload["key"] == "feeds:record"]
        self.assertEqual(jobs, ["started", "finished"])
        self.house.tick()  # the feeds have shipped: the request that asked for them is answered
        self.house.wait(10)
        self.assertEqual({row["id"]: row["status"] for row in self.house.commons._requests()}[asked["queued"]], "fulfilled")

    def test_health_json_has_a_feeds_block(self):
        self.house.tick()
        self.assertIsNone(json.loads((self.house.root / "health.json").read_text())["feeds"])
        self.attach({"perps": ["BTC"]}, transports=transport())
        self.house.tick()
        self.house.wait(10)
        self.house.tick()
        health = json.loads((self.house.root / "health.json").read_text())
        self.assertEqual((health["feeds"]["perps"]["keys"], health["feeds"]["perps"]["recording"]), (1, 1))
        self.assertIn("store_mb", health["feeds"])

    def test_research_is_told_what_is_recorded_and_not_supplied_shrinks(self):
        agent = self.seated()
        before = self.house.research_capabilities(agent)["observations"]
        self.assertNotIn("feeds", before)
        self.assertIn("live sports score feed", before["not_supplied"])
        recorder = self.attach({"sports": ["nfl"], "perps": ["BTC"]})
        self.assertIn("perpetual funding/open-interest feed", self.house.research_capabilities(agent)["observations"]["not_supplied"])
        recorder.record("perps", "BTC", started=self.clock(), finished=self.clock(), payload=perp_row(0.0001))
        observed = self.house.research_capabilities(agent)["observations"]
        self.assertNotIn("perpetual funding/open-interest feed", observed["not_supplied"])
        self.assertIn("live sports score feed", observed["not_supplied"])  # recorded nothing yet
        self.assertIn("point-in-time earnings-surprise panel", observed["not_supplied"])
        self.assertEqual((observed["feeds"]["perps"]["recording"], observed["feeds"]["perps"]["recording_since"]),
                         (["BTC"], feeds.stamp(self.clock())))
        self.assertIn("20 blocks of its horizon", observed["feeds"]["replay"])

    def test_the_feeds_have_a_lane_of_their_own(self):
        ops = self.house._lanes["ops"]
        for _ in range(self.house.settings.ops_workers):
            ops.acquire()
        try:
            ran = threading.Event()
            self.assertTrue(self.house._background("feeds:record", ran.set))
            self.assertTrue(ran.wait(5))  # a full ops lane (Merton, the backup) does not hold a scoreboard up
        finally:
            for _ in range(self.house.settings.ops_workers):
                ops.release()
        self.house.wait(5)


if __name__ == "__main__":
    unittest.main()
