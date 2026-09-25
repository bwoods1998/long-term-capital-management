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

    def recorder(self, keys, transports=None, **kw) -> FeedRecorder:
        kw.setdefault("sleep", no_sleep)
        recorder = FeedRecorder(path=Path(self.dir.name) / "feeds.sqlite", transports=transports, clock=self.clock, ledger=self.ledger,
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
             "nws_climate_report_cli": "nws", "kalshi_hourly_volume_capacity": "kalshi_candles",
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
