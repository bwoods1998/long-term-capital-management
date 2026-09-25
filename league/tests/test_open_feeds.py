"""The recorders of the key-free hosts the Kalshi-scale run added on Sept 25-26, 2026 (workstream I2 of
docs/goals/LTCM_KALSHI_SCALE.md), and the rule that answers the requests no recorder can (I3).

Every recorder is held to the three rules of league/feeds.py -- a row is visible only from the moment
it became knowable, live and in replay; a failed poll stores nothing; unchanged content is stored once
-- and to its own stamp: a climate report's issue time, a METAR's receipt, a Kalshi candle's hour end,
or the House's receive time for what the source publishes without one.
"""

import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from league import feeds  # first: league.feeds imports league.open_feeds and registers its recorders
from league import open_feeds
from league.commons import Commons
from league.feeds import FeedRecorder, request_feed, requested
from league.ledger import Ledger
from ltcm.data.kalshi_candles import CANDLES_URL, MARKETS_URL
from ltcm.data.stations import CLI_DAY_URL, CLI_YEAR_URL, METAR_URL, NCEI_URL
from ltcm.tests import test_data_kalshi_candles as kalshi_fixtures
from ltcm.tests import test_data_stations as station_fixtures
from ltcm.tests.fakes import Clock, FakeTransport, TransportError


def epoch(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def no_sleep(seconds):
    return None


class RecorderCase(unittest.TestCase):
    START = "2026-09-25T06:40:00Z"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(self.START)
        self.alerts = []
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)

    def recorder(self, keys, transports=None, path_name="feeds.sqlite", **kw) -> FeedRecorder:
        kw.setdefault("sleep", no_sleep)
        recorder = FeedRecorder(path=Path(self.dir.name) / path_name, transports=transports, clock=self.clock, ledger=self.ledger,
                                alert=lambda level, text: self.alerts.append((level, text)), keys=keys, **kw)
        self.addCleanup(recorder.close)
        return recorder

    def stamps(self, store, feed, key) -> list:
        return [at for (at,) in store.db.execute("SELECT received FROM snapshots WHERE feed = ? AND key = ? ORDER BY received", (feed, key))]


# ------------------------------------------------------------------------------ climate reports
class ClimateReports(RecorderCase):
    def transport(self, day_files=None):
        day_files = day_files if day_files is not None else {}

        def day(method, url, body):
            dt = dict(__import__("urllib.parse").parse.parse_qsl(url.split("?", 1)[1]))["dt"]
            answer = day_files.get(dt, {"type": "FeatureCollection", "features": []})
            return answer(method, url, body) if callable(answer) else answer

        def year(method, url, body):
            station = dict(__import__("urllib.parse").parse.parse_qsl(url.split("?", 1)[1]))["station"]
            if station == "KNYC":
                return station_fixtures.cli_year()
            return {"results": []}

        return FakeTransport({CLI_YEAR_URL: year, CLI_DAY_URL: day})

    def test_each_report_is_stamped_at_its_issue_and_the_preliminary_one_is_not_final(self):
        transport = self.transport()
        store = self.recorder({"cli": ["KNYC"]}, transports={"cli": transport}, backfill_pages=5)
        out = store.run()
        self.assertEqual(out["failed"], [])
        stamps = self.stamps(store, "cli", "KNYC")
        self.assertEqual(len(stamps), 15)
        self.assertEqual(feeds.stamp(stamps[-1]), "2026-09-24T20:37:00.000Z")  # the 24th's afternoon report
        row = store.latest({"cli": ["KXHIGHNY"]}, self.clock())["cli"]["KNYC"]
        self.assertEqual((row["t"], row["date"], row["high"], row["final"]), ("2026-09-24T20:37:00.000Z", "2026-09-24", 66.0, False))
        before = store.latest({"cli": ["KNYC"]}, epoch("2026-09-24T20:36:59Z"))["cli"]["KNYC"]
        self.assertEqual((before["date"], before["issued"], before["final"], before["high"]), ("2026-09-23", "2026-09-24T06:17:00Z", True, 67.0))
        state = store.coverage({"cli": ["KNYC"]})["cli"]["KNYC"]["backfill"]
        self.assertTrue(state["complete"], state)
        self.assertEqual([c["query"].get("year") for c in transport.calls if "year" in c["query"]], ["2026", "2026"])

    def test_a_live_pass_reads_two_day_files_for_every_station_and_adds_the_final_report(self):
        final = copy.deepcopy(station_fixtures.cli_day())
        for feature in final["features"]:
            if feature["properties"]["station"] == "KNYC":
                feature["properties"].update(product="202609250617-KOKX-CDUS41-CLINYC", high=67, low=53)
        files = {"2026-09-24": station_fixtures.cli_day()}
        transport = self.transport(files)
        store = self.recorder({"cli": ["KNYC"]}, transports={"cli": transport})
        store.run()
        self.clock.set("2026-09-25T07:10:00Z")
        files["2026-09-24"] = final
        calls = len(transport.calls)
        store._keys = {"cli": ["KNYC", "KMDW", "KDEN"]}
        out = store.run()
        day_calls = [c["query"]["dt"] for c in transport.calls[calls:] if "dt" in c["query"]]
        self.assertEqual(sorted(day_calls), ["2026-09-24", "2026-09-25"])  # two requests for three stations
        self.assertIn("cli", out["polled"])
        row = store.latest({"cli": ["KNYC"]}, self.clock())["cli"]["KNYC"]
        self.assertEqual((row["t"], row["high"], row["final"]), ("2026-09-25T06:17:00.000Z", 67.0, True))
        self.assertEqual(store.latest({"cli": ["KNYC"]}, epoch("2026-09-25T06:16:59Z"))["cli"]["KNYC"]["final"], False)

    def test_a_failed_day_file_fails_the_pass_once_and_stores_nothing(self):
        transport = self.transport({"2026-09-24": station_fixtures.cli_day()})
        store = self.recorder({"cli": ["KNYC"]}, transports={"cli": transport})
        store.run()
        held = len(self.stamps(store, "cli", "KNYC"))
        down = FakeTransport({CLI_DAY_URL: TransportError("GET https://mesonet.agron.iastate.edu/geojson/cli.py?dt=x failed: timed out")})
        store._fetchers.pop("cli")
        store._transports = {"cli": down}
        store._keys = {"cli": ["KNYC", "KMDW"]}
        self.clock.set("2026-09-25T07:10:00Z")
        # KMDW has nothing held: its first page reads its year file, which the down host fails too
        down.route(CLI_YEAR_URL, TransportError("GET https://mesonet.agron.iastate.edu/json/cli.py failed: timed out"))
        out = store.run()
        self.assertEqual({k for f, k, _ in out["failed"] if f == "cli"}, {"KMDW", "KNYC"})
        self.assertEqual(len(self.stamps(store, "cli", "KNYC")), held)
        self.assertEqual(len([c for c in down.calls if "dt" in c["query"]]), 1)  # the failure is remembered for the pass

    def test_a_station_the_mesonet_does_not_hold_is_not_listed(self):
        store = self.recorder({"cli": ["KMDW"]}, transports={"cli": self.transport()})
        out = store.run()
        self.assertTrue(out["failed"] and feeds.NOT_LISTED in out["failed"][0][2], out["failed"])
        self.assertEqual(self.alerts, [])


# ------------------------------------------------------------------------------------ METARs
class Metars(RecorderCase):
    def transport(self):
        def answer(method, url, body):
            query = dict(__import__("urllib.parse").parse.parse_qsl(url.split("?", 1)[1]))
            if "date" in query:
                return station_fixtures.metars_dated() if query["date"] >= "2026-09-20" else []
            return station_fixtures.metars()

        return FakeTransport({METAR_URL: answer})

    def test_one_request_answers_every_station_and_each_row_is_stamped_at_receipt(self):
        transport = self.transport()
        store = self.recorder({"metar": ["KNYC", "KMDW", "KAUS"]}, transports={"metar": transport}, backfill_pages=1)
        store.run()
        heads = [c for c in transport.calls if "date" not in c["query"]]
        self.assertEqual(len(heads), 1)
        self.assertEqual(heads[0]["query"]["ids"], "KNYC,KMDW,KAUS")
        stamps = [feeds.stamp(at) for at in self.stamps(store, "metar", "KNYC")]
        self.assertIn("2026-09-25T05:54:11.152Z", stamps)
        row = store.latest({"metar": ["KXHIGHNY"]}, self.clock())["metar"]["KNYC"]
        self.assertEqual((row["t"], row["observed"]), ("2026-09-25T05:54:11.152Z", "2026-09-25T05:51:00Z"))
        self.assertNotIn("received_at", row)
        earlier = store.latest({"metar": ["KNYC"]}, epoch("2026-09-25T05:54:11.151Z"))["metar"]["KNYC"]
        self.assertEqual(earlier["t"], "2026-09-25T04:54:14.483Z")  # a report is never shown before it was received

    def test_the_backfill_pages_back_from_the_oldest_row_to_the_services_thirty_days(self):
        transport = self.transport()
        store = self.recorder({"metar": ["KNYC"]}, transports={"metar": transport}, backfill_pages=40)
        store.run()
        dated = [c["query"] for c in transport.calls if "date" in c["query"]]
        self.assertTrue(dated)
        self.assertEqual(dated[0]["hours"], "72")
        self.assertEqual(dated[0]["date"], "2026-09-25T03:54:13Z")  # from the oldest receipt held, back
        self.assertIn(epoch("2026-09-19T23:54:13.824Z"), self.stamps(store, "metar", "KNYC"))
        state = store.coverage({"metar": ["KNYC"]})["metar"]["KNYC"]["backfill"]
        self.assertTrue(state["complete"], state)  # the service's history ends: the backfill stops
        self.assertEqual(feeds.RECORDERS["metar"].backfill_days, 29.0)


# ---------------------------------------------------------------------------- daily summaries
class Summaries(RecorderCase):
    def test_one_request_for_every_station_stamped_at_receipt_and_stored_once(self):
        transport = FakeTransport({NCEI_URL: station_fixtures.summaries()})
        store = self.recorder({"ghcnd": ["KNYC", "KMDW", "KDEN"]}, transports={"ghcnd": transport})
        out = store.run()
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("ghcnd", "KDEN")])  # no rows for it in the answer
        row = store.latest({"ghcnd": ["KNYC"]}, self.clock())["ghcnd"]["KNYC"]
        self.assertEqual((row["t"], row["ghcnd"], row["latest"]["date"]), ("2026-09-25T06:40:00.000Z", "USW00094728", "2026-09-22"))
        self.assertEqual(store.latest({"ghcnd": ["KNYC"]}, self.clock() - 0.001), {})
        self.clock.advance(6 * 3600)
        store.run()
        self.assertEqual(store.coverage({"ghcnd": ["KNYC"]})["ghcnd"]["KNYC"]["snapshots"], 1)


# ---------------------------------------------------------------------------- Kalshi candles
class KalshiCandles(RecorderCase):
    START = "2026-09-25T00:40:00Z"

    def transport(self):
        return FakeTransport({MARKETS_URL: kalshi_fixtures.markets(), CANDLES_URL: kalshi_fixtures.candles()})

    def test_an_hour_is_a_row_stamped_at_its_end_and_the_running_hour_is_never_stored(self):
        transport = self.transport()
        store = self.recorder({"kalshi_candles": ["KXHIGHNY"]}, transports={"kalshi_candles": transport}, backfill_pages=1)
        out = store.run()
        self.assertEqual(out["failed"], [])
        stamps = self.stamps(store, "kalshi_candles", "KXHIGHNY")
        self.assertEqual(feeds.stamp(stamps[-1]), "2026-09-25T00:00:00.000Z")  # 00:00-01:00 is still running at 00:40
        self.assertEqual({b - a for a, b in zip(stamps, stamps[1:])}, {3600.0})
        row = store.latest({"kalshi_candles": ["kxhighny"]}, epoch("2026-09-24T20:00:00Z"))["kalshi_candles"]["KXHIGHNY"]
        self.assertEqual((row["t"], row["hour_start"], row["series"]), ("2026-09-24T20:00:00.000Z", "2026-09-24T19:00:00.000Z", "KXHIGHNY"))
        found = kalshi_fixtures.candles()["markets"]
        expected = sum(float(c["volume_fp"]) for m in found for c in m["candlesticks"] if c["end_period_ts"] == epoch("2026-09-24T20:00:00Z"))
        self.assertAlmostEqual(row["volume"], round(expected, 2))
        self.assertEqual(row["markets_listed"], row["markets_read"])
        self.assertTrue(all(set(m) == {"volume", "open_interest", "open", "high", "low", "close", "bid", "ask"} for m in row["markets"].values()))
        listing = [c for c in transport.calls if c["path"].endswith("/markets")]
        self.assertEqual(listing[0]["query"]["series_ticker"], "KXHIGHNY")

    def test_an_hours_counts_read_only_markets_listed_by_its_end(self):
        """Review of #309 (Sept 25, 2026): markets_listed and markets_read were one count for the page's 24 rows,
        so the 10:00Z row counted the markets Kalshi listed at 14:00Z that day."""
        from ltcm.data.kalshi_candles import parse_markets

        store = self.recorder({"kalshi_candles": ["KXHIGHNY"]}, transports={"kalshi_candles": self.transport()}, backfill_pages=1)
        store.run()
        listed, _ = parse_markets(kalshi_fixtures.markets())
        rows = {}
        for hour in ("2026-09-24T10:00:00Z", "2026-09-24T20:00:00Z"):
            end = epoch(hour)
            rows[hour] = store.latest({"kalshi_candles": ["KXHIGHNY"]}, end)["kalshi_candles"]["KXHIGHNY"]
            open_then = sum(1 for m in listed if m["open"] < end and (m["close"] is None or m["close"] > end - 3600))
            self.assertEqual(rows[hour]["markets_listed"], open_then, hour)
        self.assertLess(rows["2026-09-24T10:00:00Z"]["markets_listed"], rows["2026-09-24T20:00:00Z"]["markets_listed"])
        self.assertTrue(all(ticker in {m["ticker"] for m in listed if m["open"] < epoch("2026-09-24T10:00:00Z")}
                            for ticker in rows["2026-09-24T10:00:00Z"]["markets"]))

    def test_the_backfill_reaches_fourteen_days_a_day_a_page(self):
        transport = self.transport()
        store = self.recorder({"kalshi_candles": ["KXHIGHNY"]}, transports={"kalshi_candles": transport}, backfill_pages=40)
        store.run()
        stamps = self.stamps(store, "kalshi_candles", "KXHIGHNY")
        self.assertLessEqual(stamps[0], self.clock() - 14 * 86400.0 + 3600.0)
        self.assertEqual(len(stamps), len(set(stamps)))
        state = store.coverage({"kalshi_candles": ["KXHIGHNY"]})["kalshi_candles"]["KXHIGHNY"]["backfill"]
        self.assertTrue(state["complete"], state)
        candle_calls = [c for c in transport.calls if c["path"].endswith("/candlesticks")]
        self.assertLessEqual(len(candle_calls), 16)  # a day a page: fifteen or so requests for two weeks

    def test_the_series_follow_the_kalshi_desks_crypto_left_out(self):
        from league import niches

        store = FeedRecorder(path=Path(self.dir.name) / "desks.sqlite", clock=self.clock, niches=niches.load())
        self.addCleanup(store.close)
        keys = store.keys("kalshi_candles")
        self.assertEqual(len(keys), 16)
        self.assertEqual(keys[:2], ["KXNCAAFGAME", "KXRAIN"])  # sports first, then weather, round robin
        self.assertFalse([k for k in keys if k.startswith(("KXBTC", "KXETH"))])
        self.assertEqual(requested({"kalshi_candles": ["KXMLBGAME", "kxhighny", "KXBTCD", "nfl"]}), {"kalshi_candles": ["KXMLBGAME", "KXHIGHNY"]})


# ------------------------------------------------------------------------------ vocabulary
class WhatIsDeclared(RecorderCase):
    def test_needs_accept_the_new_feeds_by_station_series_or_city(self):
        self.assertEqual(requested({"cli": ["KXHIGHNY", "chicago", "KXBTCD"], "metar": ["KNYC", "KXLOWTNYC"], "ghcnd": ["KXHIGHTPHX"],
                                    "kalshi_candles": ["KXNFLGAME"]}),
                         {"cli": ["KNYC", "KMDW"], "metar": ["KNYC"], "ghcnd": ["KPHX"], "kalshi_candles": ["KXNFLGAME"]})
        self.assertEqual(set(open_feeds.SOURCES[i].name for i in range(len(open_feeds.SOURCES))) - set(feeds.FEEDS), set())
        self.assertIn("cli", feeds.HISTORY_FEEDS)
        self.assertNotIn("ghcnd", feeds.HISTORY_FEEDS)

    def test_requests_name_the_new_feeds_in_their_own_words(self):
        self.assertEqual({name: request_feed(name) for name in (
            "weather_station_observations_history", "metar_feed", "settlement_station_observed_high", "nws_climate_report_cli",
            "kalshi_hourly_volume_capacity", "kalshi_candles_history", "ghcnd_daily_summaries", "kalshi_open_interest_history")},
            {"weather_station_observations_history": "metar", "metar_feed": "metar", "settlement_station_observed_high": "cli",
             "nws_climate_report_cli": "cli", "kalshi_hourly_volume_capacity": "kalshi_candles",
             "kalshi_candles_history": "kalshi_candles", "ghcnd_daily_summaries": "ghcnd", "kalshi_open_interest_history": None})

    def test_describe_health_and_every_host_on_record(self):
        store = self.recorder({"ghcnd": ["KNYC"]}, transports={"ghcnd": FakeTransport({NCEI_URL: station_fixtures.summaries()})})
        store.run()
        described = store.describe()
        self.assertEqual((described["ghcnd"]["host"], described["cli"]["host"]), ("www.ncei.noaa.gov", "mesonet.agron.iastate.edu"))
        self.assertIn("issue time", described["cli"]["point_in_time"])
        self.assertIn("receive time", described["ghcnd"]["point_in_time"])
        self.assertEqual(store.health()["ghcnd"]["recording"], 1)
        hosts = feeds.league_hosts()
        for source in open_feeds.SOURCES:
            self.assertIn(source.host, hosts, source.name)


# ------------------------------------------------------------------------------ refusals (I3)
class Refusals(RecorderCase):
    ASKED = {  # the open requests of Sept 24-25, 2026 the coordinator named, and two a recorder answers
        "hufschmid-39": "mlb_point_in_time_lineup_pitcher_feed",
        "rosenfeld-h35c05b": "historical_external_crypto_indexes",
        "hufschmid-38": "mlb_player_prop_reference_history",
        "haghani-l22bffc": "crypto_spot_rebalance_events",
        "mullins-7": "polymarket_cross_venue_prices",
        "mullins-8": "settlement_station_observed_high",
        "mullins-9": "weather_ensemble_forecasts",
        "meriwether-1": "something_nobody_publishes_here",
    }

    def ask(self, commons):
        return {name: commons.request_tool(agent, name, "the data this line needs to price its markets")["queued"]
                for agent, name in self.ASKED.items()}

    def test_the_open_requests_no_recorder_answers_are_refused_by_rule_once(self):
        commons = Commons(self.ledger, clock=self.clock)
        ids = self.ask(commons)
        store = self.recorder({"ghcnd": ["KNYC"]})
        refused = store.fulfil_requests(commons)  # nothing recorded yet: only refusals
        self.assertEqual(sorted(refused), sorted(ids[n] for n in ("mlb_point_in_time_lineup_pitcher_feed", "historical_external_crypto_indexes",
                                                                   "mlb_player_prop_reference_history", "crypto_spot_rebalance_events",
                                                                   "polymarket_cross_venue_prices")))
        rows = {row["id"]: row for row in commons.blocked_requests()}
        self.assertEqual(rows[ids["mlb_player_prop_reference_history"]]["owner"], "owner")  # a paid key: the owner's step
        self.assertEqual(rows[ids["polymarket_cross_venue_prices"]]["owner"], "no-source")
        self.assertIn("Refused by rule", rows[ids["polymarket_cross_venue_prices"]]["outcome"])
        self.assertIn("proprietary trading", rows[ids["polymarket_cross_venue_prices"]]["outcome"])
        self.assertIn("statsapi", rows[ids["mlb_point_in_time_lineup_pitcher_feed"]]["outcome"])
        open_names = {row["name"] for row in commons.open_requests(stale_days=0)}
        self.assertEqual(open_names, {"settlement_station_observed_high", "weather_ensemble_forecasts", "something_nobody_publishes_here"})
        self.assertEqual(store.fulfil_requests(commons), [])  # idempotent
        self.assertEqual(len(list(self.ledger.iter(kinds="tool.blocked"))), 5)

    def test_a_recorded_feed_still_fulfils_and_refusals_follow(self):
        commons = Commons(self.ledger, clock=self.clock)
        ids = self.ask(commons)
        cli = {"2026-09-24": station_fixtures.cli_day()}
        store = self.recorder({"cli": ["KNYC"]}, transports={"cli": ClimateReports.transport(self, cli)})
        store.run()
        done = store.fulfil_requests(commons)
        self.assertEqual(done[0], ids["settlement_station_observed_high"])  # fulfilled first, then the refusals
        self.assertEqual(len(done), 6)
        answer = [e for e in self.ledger.iter(kinds="tool.fulfilled")][-1].payload["outcome"]
        self.assertIn("NEEDS['feeds'] = {'cli': ['KXHIGHNY']}", answer)

    def test_every_refusal_names_its_rule_and_owner(self):
        for rule in open_feeds.REFUSALS:
            self.assertIn(rule.owner, ("owner", "no-source"), rule.name)
            self.assertTrue(rule.rule and rule.needs, rule.name)
        self.assertIsNone(open_feeds.refusal_for("options_gamma_exposure"))
        self.assertIsNone(open_feeds.refusal_for(""))
        self.assertEqual(open_feeds.refusal_for("vix_term_structure").name, "cboe")
        self.assertEqual(open_feeds.refusal_for("fred_dgs10_daily").owner, "owner")
        named = {name: (open_feeds.refusal_for(name).name, open_feeds.refusal_for(name).owner) for name in (
            "openrouter_rankings", "ai_model_token_share", "cpi_consensus_forecast", "gdpnow_nowcast", "cleveland_fed_inflation_nowcast",
            "truth_social_post_count", "manifold_prices", "coingecko_prices", "f1_race_results", "nba_player_stats")}
        self.assertEqual(named, {"openrouter_rankings": ("openrouter", "owner"), "ai_model_token_share": ("ai_share", "owner"),
                                 "cpi_consensus_forecast": ("econ_consensus", "no-source"), "gdpnow_nowcast": ("gdpnow", "no-source"),
                                 "cleveland_fed_inflation_nowcast": ("inflation_nowcast", "no-source"),
                                 "truth_social_post_count": ("truth_social_count", "no-source"),
                                 "manifold_prices": ("prediction_venues", "no-source"), "coingecko_prices": ("crypto_aggregators", "owner"),
                                 "f1_race_results": ("f1", "no-source"), "nba_player_stats": ("league_stats", "no-source")})

    def test_a_request_a_recorder_answers_is_never_refused(self):
        commons = Commons(self.ledger, clock=self.clock)
        asked = commons.request_tool("leahy-3", "openrouter_pageviews", "attention on OpenRouter while KXTOKENUSE trades")["queued"]
        self.assertIsNotNone(open_feeds.refusal_for("openrouter_pageviews"))  # a rule names it ...
        self.assertEqual(request_feed("openrouter_pageviews"), "pageviews")  # ... but a recorder answers it
        self.assertEqual(open_feeds.refuse_requests(commons), [])
        self.assertEqual([row["id"] for row in commons.open_requests(stale_days=0)], [asked])

    def test_a_restart_refuses_nothing_twice(self):
        commons = Commons(self.ledger, clock=self.clock)
        self.ask(commons)
        self.assertEqual(len(self.recorder({"ghcnd": ["KNYC"]}).fulfil_requests(commons)), 5)
        again = Commons(self.ledger, clock=self.clock)  # a new release: the queue is read back from the ledger
        self.assertEqual(open_feeds.refuse_requests(again), [])
        blocked = [entry.payload["request"] for entry in self.ledger.iter(kinds="tool.blocked")]
        self.assertEqual(len(blocked), len(set(blocked)))

    def test_a_request_goes_to_the_feed_that_records_it_and_the_rule_it_fails(self):
        """Review of #309 (Sept 25, 2026): the NWS forecast took every request naming "nws", the keyed `eia` feed
        (nothing recorded without the owner's key) took the requests `fuel` records key-free, and BEA's "advance
        estimate" read as an economists' consensus -- the owner's key, not "no-source"."""
        self.assertEqual({name: request_feed(name) for name in (
            "nws_climate_report_cli", "nws_point_forecast", "nws_cli_raw_text", "eia_gasoline_weekly", "brent_spot_daily",
            "gas_price_aaa_daily", "consensus_win_probabilities_sports")},
            {"nws_climate_report_cli": "cli", "nws_point_forecast": "nws", "nws_cli_raw_text": "cli",
             "eia_gasoline_weekly": "fuel", "brent_spot_daily": "fuel", "gas_price_aaa_daily": None,
             "consensus_win_probabilities_sports": "consensus"})
        rules = {name: (open_feeds.refusal_for(name).name, open_feeds.refusal_for(name).owner) for name in (
            "gdp_advance_estimate_values", "nonfarm_payrolls_consensus_estimate", "gas_price_aaa_daily", "mlb_probable_pitchers",
            "sportsbook_line_movement_history", "coinbase_spot_candles", "hyperliquid_oracle_price_history")}
        self.assertEqual(rules, {"gdp_advance_estimate_values": ("bea_data", "owner"),
                                 "nonfarm_payrolls_consensus_estimate": ("econ_consensus", "no-source"),
                                 "gas_price_aaa_daily": ("aaa_gas", "no-source"), "mlb_probable_pitchers": ("lineups", "no-source"),
                                 "sportsbook_line_movement_history": ("odds_history", "owner"),
                                 "coinbase_spot_candles": ("exchange_terms", "no-source"),
                                 "hyperliquid_oracle_price_history": ("crypto_index_history", "no-source")})


# ------------------------------------------------------------------ the lane and the hosts (review of #309)
class LaneAndHosts(RecorderCase):
    """The feeds lane has one slot, shared with the sports boards the Kalshi founders price from: a host that
    hangs must cost it a timeout once a backoff at most, never once a key (Sept 25, 2026, 10:41Z: GDELT's TLS
    handshake timed out after 15 s from the House box)."""

    def hung(self, message="_ssl.c:1011: The handshake operation timed out", seconds=30.0):
        clock, calls = self.clock, []

        def hang(method, url, body):
            calls.append(url)
            clock.advance(seconds)
            return TransportError(f"{method} {url.split('?')[0]} failed: {message}")

        return FakeTransport(default=hang), calls

    def test_a_host_that_cannot_be_reached_costs_one_timeout_a_backoff_and_warns_hourly(self):
        from ltcm.data.signals import GDELT_DOC_URL

        transport, calls = self.hung()
        subjects = list(open_feeds.GDELT_QUERIES)
        store = self.recorder({"gdelt": subjects}, transports={"gdelt": transport})
        out = store.run()
        self.assertEqual(len(calls), 1)  # eight subjects, one request: the other seven were not asked
        self.assertTrue(calls[0].startswith(GDELT_DOC_URL))
        self.assertEqual(sorted(k for f, k, _ in out["failed"]), sorted(subjects))
        self.assertEqual(sorted(store.health()["gdelt"]["failing"]), sorted(subjects))
        for _ in range(180):  # three hours of the House's minute tick
            self.clock.advance(60)
            if store.due():
                store.run()
        self.assertLessEqual(len(calls), 6)  # asked again after 5, 10, 20, 40, 80 minutes: never every five minutes
        self.assertLessEqual(len(calls) * 30.0, 0.05 * 3 * 3600 + 30.0)
        self.assertTrue(self.alerts and all(level == "warning" for level, _ in self.alerts))  # never an error: no rollback
        gdelt = [text for _, text in self.alerts if " gdelt " in text]
        self.assertLessEqual(len(gdelt), 3)  # at most hourly
        self.assertEqual(self.stamps(store, "gdelt", "bitcoin"), [])

    def test_a_server_that_answers_again_is_asked_at_once(self):
        from ltcm.tests import test_data_hazards as hazard_fixtures

        transport, calls = self.hung(message="[Errno 111] Connection refused", seconds=0.0)
        store = self.recorder({"quakes": ["m4.5_day", "significant_week"]}, transports={"quakes": transport})
        store.run()
        self.assertEqual(len(calls), 1)
        self.clock.advance(300)
        transport.default = lambda method, url, body: hazard_fixtures.quakes()
        store.run()
        self.assertEqual(len(calls), 1)  # the handler that counts is gone: the host answered
        self.assertEqual(sorted(store.latest({"quakes": ["m4.5_day", "significant_week"]}, self.clock())["quakes"]),
                         ["m4.5_day", "significant_week"])
        self.assertIsNone(store._host_wait("quakes", self.clock()))

    def test_one_slow_key_is_its_own_failure_but_a_hung_server_backs_off(self):
        transport, calls = self.hung(message="The read operation timed out", seconds=20.0)
        store = self.recorder({"pageviews": ["bitcoin", "ethereum", "trump", "fed"]}, transports={"pageviews": transport},
                              backfill_pages=1)
        store.run()
        self.assertEqual(len(calls), 2)  # two keys that did not answer: the server hangs, the other two are not asked
        self.clock.advance(60)
        store.run()
        self.assertEqual(len(calls), 2)  # nor the backfill, while the host backs off
        # One filer that times out while the others answer (EDGAR's pattern) never holds the host back.
        slow = FakeTransport({feeds_url("trump"): TransportError("GET x failed: The read operation timed out")},
                             default=lambda method, url, body: {"items": []})
        other = self.recorder({"pageviews": ["bitcoin", "trump", "fed"]}, transports={"pageviews": slow}, path_name="other.sqlite",
                              backfill_pages=1)
        other.run()
        asked = {url.split("/user/")[1].split("/")[0] for url in (c["url"] for c in slow.calls)}
        self.assertEqual(asked, {"Bitcoin", "Donald_Trump", "Federal_Reserve"})
        self.assertIsNone(other._host_wait("pageviews", self.clock()))

    def test_a_history_recorder_gives_way_to_a_due_board_before_its_first_key(self):
        transport, calls = self.hung(seconds=0.0)
        store = self.recorder({"sports": ["nfl"], "cli_text": ["KNYC"]}, transports={"cli_text": transport})
        store._schedule("sports", "nfl", self.clock())  # the board is due
        out = {"polled": [], "stored": 0, "failed": []}
        store._poll_history("cli_text", out)
        self.assertEqual(calls, [])
        self.assertLessEqual(store._next[("cli_text", "*")], self.clock())  # due again at once, behind the board

    def test_a_restart_does_not_spend_blss_queries(self):
        from ltcm.data.releases import BLS_V1_URL
        from ltcm.tests import test_data_releases as release_fixtures

        transport = FakeTransport({("POST", BLS_V1_URL): release_fixtures.bls()})
        store = self.recorder({"bls": ["CPI", "UNRATE"]}, transports={"bls": transport})
        store.run()
        self.assertEqual(len(transport.calls), 1)
        self.clock.advance(600)
        again = self.recorder({"bls": ["CPI", "UNRATE"]}, transports={"bls": transport})  # a release restarts the House
        again.run()
        self.assertEqual(len(transport.calls), 1)  # 25 keyless queries a day: polled ten minutes ago, due in eighty
        self.clock.advance(5400 - 600)
        again.run()
        self.assertEqual(len(transport.calls), 2)

    def test_a_failed_bls_query_is_asked_again_in_forty_five_minutes(self):
        from ltcm.data.releases import BLS_V1_URL

        transport = FakeTransport({("POST", BLS_V1_URL): (503, {}, b"Service Unavailable")})
        store = self.recorder({"bls": ["CPI"]}, transports={"bls": transport})
        store.run()
        for _ in range(44):
            self.clock.advance(60)
            store.run()
        self.assertEqual(len(transport.calls), 1)
        self.clock.advance(60)
        store.run()
        self.assertEqual(len(transport.calls), 2)

    def test_timeouts_stay_under_the_lane_and_every_recorder_host_is_allowed(self):
        hosts = feeds.league_hosts()
        for source in open_feeds.SOURCES:
            self.assertLessEqual(source.timeout, 45.0, source.name)
            self.assertIn(source.host, hosts, source.name)


def feeds_url(subject: str) -> str:
    from ltcm.data.signals import PAGEVIEWS_URL

    return f"{PAGEVIEWS_URL}/{open_feeds.ATTENTION[subject][0]}/*"


class ImportOrder(unittest.TestCase):
    def test_either_module_first_gives_one_registered_set(self):
        import subprocess
        import sys

        code = ("import league.open_feeds as o, league.feeds as f; "
                "print(all(f.RECORDERS[s.name] is s for s in o.SOURCES), o is f._open_feeds)")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))
        self.assertEqual(out.stdout.strip(), "True True", out.stderr[-600:])


if __name__ == "__main__":
    unittest.main()
