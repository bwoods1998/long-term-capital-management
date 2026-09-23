"""Live feeds: ESPN scoreboards and perpetual funding, recorded with the House's receive time.

Sept 22, 2026: 43 agents had asked for live sports scores and 32 for perp funding or open
interest, and nothing in the league supplied either. These tests hold the recorder to its three
rules -- point in time, nothing fabricated, unchanged content stored once -- and the House to its
hooks: `ctx["feeds"]` only when declared, a replay only once the feeds are recorded long enough
(and no trial before), a lane of its own that runs while paused, and a block in health.json.
"""

import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

from league import feeds, niches
from league.commons import Commons
from league.feeds import FeedRecorder, request_feed, requested
from league.ledger import Ledger
from league.replay import run_replay
from league.tests.test_house import BUYER, HouseCase
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
        self.assertEqual([call["url"] for call in fake.calls], [NFL, EPL])
        self.assertTrue(all("dates" not in call["query"] for call in fake.calls))  # today's board, never a past one
        board = store.latest({"sports": ["nfl", "epl"]}, self.clock())["sports"]
        self.assertEqual((board["nfl"]["espn"], [e["id"] for e in board["nfl"]["events"]]), ("football/nfl", ["401872932", "401872933"]))
        self.assertEqual((board["epl"]["events"][0]["status"], board["epl"]["events"][0]["home"]["score"]), ("in", 1))
        self.assertEqual(board["nfl"]["t"], "2026-09-22T12:00:00.000Z")

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
                                    "PERPS": ["btc/usd", "XBT", "ethusdt", "PEPE"], "weather": ["KXHIGHNY"]}),
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


class InTheHouse(HouseCase):
    def attach(self, keys, transports=None) -> FeedRecorder:
        recorder = FeedRecorder(self.house, Path(self.dir.name) / "feeds.sqlite", transports, keys=keys)
        self.house.feeds = recorder
        self.addCleanup(recorder.close)  # also when a test takes it off the House
        return recorder

    def history(self, recorder, first: str, last: str, every: float = 300.0, offset: float = 137.4) -> list[float]:
        """Successful BTC polls from `first` to `last`, received `offset` seconds into each interval."""
        at, stop, received = epoch(first) + offset, epoch(last), []
        while at <= stop:
            recorder.record("perps", "BTC", started=at - 2, finished=at, payload=perp_row(round(at % 100000, 3)))
            received.append(at)
            at += every
        return received

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
