"""The recorders of Sept 24, 2026 (docs/goals/LTCM_CLOSE_THE_GAPS.md, workstream I, gap 7): the data
hosts the owner allowed that morning, recorded for the strategies that asked for them.

Gap 7's evidence: earnings calendars, settlement fixings, attention underlyings and weather ensembles
were owner egress steps, the attention desk had no intent in 48 hours, and alpaca-crypto-majors was
offered markets on 42-45 wakes an hour with no intent. These tests hold every new recorder to the
three rules of `league/feeds.py` -- a row is visible only from the moment it became knowable, live
and in replay; a failed poll stores nothing; unchanged content is stored once -- and to its own
stamp: the House's receive time for what the source publishes without one, the source's own final
time (an 8-K's acceptance, an interval's end, a forecast's issue plus its publication allowance)
for what is backfilled.
"""

import json
import math
import tempfile
import unittest
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from league import feeds, niches
from league.commons import Commons
from league import feeds as feeds_module
from league.feeds import UNCHANGED, FeedRecorder, request_feed, requested
from league.ledger import Ledger
from league.replay import run_replay
from league.tests.test_house import HouseCase
from ltcm.data.openmeteo import ENSEMBLE_HOST, HISTORICAL_HOST
from ltcm.tests.fakes import Clock, FakeTransport, TransportError


def epoch(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def no_sleep(seconds):
    return None


def query(url: str) -> dict:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


class Meteo:
    """An Open-Meteo that answers from synthetic weather, the way the recorded payloads are shaped
    (ltcm/tests/fixtures/feeds): the ensemble for four UTC days from today, the archive of lead-N
    forecasts for any UTC dates, and each run model's meta.json, whose run the test moves."""

    MODELS = {"gfs_seamless": ("ncep_gefs_seamless", 3), "ecmwf_ifs025": ("ecmwf_ifs025_ensemble", 2)}

    def __init__(self, clock):
        self.clock = clock
        self.run_at = epoch("2026-09-23T12:00:00Z")  # the newest run's start; available six hours later
        self.shift = 0.0  # what a newer run changes in every value
        self.asked: list = []

    @staticmethod
    def temperature(valid: float, lead: int = 0, model: str = "gfs_seamless", member: int = 0) -> float:
        hour = datetime.fromtimestamp(valid, timezone.utc).hour
        return round(55.0 + hour * 0.5 + lead * 0.25 + (1.0 if model == "ecmwf_ifs025" else 0.0) + member * 0.1, 1)

    def meta(self, run_model):
        def answer(method, url, body):
            self.asked.append(("meta", run_model))
            return {"last_run_initialisation_time": self.run_at, "last_run_availability_time": self.run_at + 6 * 3600,
                    "last_run_modification_time": self.run_at + 6 * 3600, "update_interval_seconds": 21600}
        return answer

    def ensemble(self, method, url, body):
        self.asked.append(("ensemble", query(url)["latitude"]))
        start = math.floor(self.clock() / 86400.0) * 86400.0
        hours = [start + 3600 * i for i in range(24 * int(query(url)["forecast_days"]))]
        hourly = {"time": [datetime.fromtimestamp(h, timezone.utc).strftime("%Y-%m-%dT%H:%M") for h in hours]}
        for name, (suffix, count) in self.MODELS.items():
            for member in range(count):
                tag = f"_member{member:02d}" if member else ""
                hourly[f"temperature_2m{tag}_{suffix}"] = [self.temperature(h, 0, name, member) + self.shift for h in hours]
                hourly[f"precipitation{tag}_{suffix}"] = [0.01 if datetime.fromtimestamp(h, timezone.utc).hour == 12 else 0.0 for h in hours]
        return {"latitude": 40.75, "longitude": -74.0, "utc_offset_seconds": 0, "timezone": "GMT", "hourly": hourly}

    def archive(self, method, url, body):
        q = query(url)
        self.asked.append(("archive", q["start_date"], q["end_date"]))
        first = epoch(q["start_date"] + "T00:00:00Z")
        last = epoch(q["end_date"] + "T23:00:00Z")
        hours = [first + 3600 * i for i in range(int((last - first) / 3600) + 1)]
        hourly = {"time": [datetime.fromtimestamp(h, timezone.utc).strftime("%Y-%m-%dT%H:%M") for h in hours]}
        for variable in q["hourly"].split(","):
            lead = int(variable.rsplit("previous_day", 1)[1])
            for model in q["models"].split(","):
                if variable.startswith("temperature_2m"):
                    hourly[f"{variable}_{model}"] = [self.temperature(h, lead, model) for h in hours]
                else:
                    hourly[f"{variable}_{model}"] = [0.02 * lead for h in hours]
        return {"latitude": 40.79, "longitude": -73.97, "utc_offset_seconds": 0, "timezone": "GMT", "hourly": hourly}

    def routes(self) -> dict:
        return {ENSEMBLE_HOST + "/data/ncep_gefs025/static/meta.json": self.meta("ncep_gefs025"),
                ENSEMBLE_HOST + "/data/ecmwf_ifs025_ensemble/static/meta.json": self.meta("ecmwf_ifs025_ensemble"),
                ENSEMBLE_HOST + "/v1/ensemble?*": self.ensemble,
                HISTORICAL_HOST + "/v1/forecast?*": self.archive}

    def transport(self) -> FakeTransport:
        return FakeTransport(self.routes())


class RecorderCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock("2026-09-24T03:30:00Z")
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


# ---------------------------------------------------------------------------------- weather
class Weather(RecorderCase):
    def test_the_ensemble_is_recorded_per_station_with_its_runs_and_shown_only_from_receipt(self):
        meteo = Meteo(self.clock)
        store = self.recorder({"weather": ["KNYC", "KLAX"]}, transports={"weather": meteo.transport()})
        out = store.run()
        self.assertEqual(out["failed"], [])
        self.assertEqual(out["polled"], ["weather:KNYC", "weather:KLAX"])
        row = store.latest({"weather": ["KNYC"]}, self.clock())["weather"]["KNYC"]
        self.assertEqual(row["t"], "2026-09-24T03:30:00.000Z")  # received, never the run's own times
        self.assertEqual(row["runs"]["gfs_seamless"], {"model": "ncep_gefs025", "init": "2026-09-23T12:00:00Z",
                                                        "available": "2026-09-23T18:00:00Z", "modified": "2026-09-23T18:00:00Z"})
        self.assertEqual(sorted(row["runs"]), ["ecmwf_ifs025", "gfs_seamless"])
        # Three whole climate days (local STANDARD time: New York's Sept 24 runs 05:00Z to 04:00Z).
        self.assertEqual(sorted(row["dates"]), ["2026-09-24", "2026-09-25", "2026-09-26"])
        day = row["dates"]["2026-09-25"]
        self.assertEqual(day["high"]["n"], 5)  # the control and two members of GEFS, the control and one of ECMWF
        hours = [epoch("2026-09-25T05:00:00Z") + 3600 * i for i in range(24)]
        self.assertEqual(day["high"]["max"], max(Meteo.temperature(h, 0, "ecmwf_ifs025", 1) for h in hours))
        self.assertEqual(day["low"]["min"], min(Meteo.temperature(h, 0, "gfs_seamless", 0) for h in hours))
        self.assertEqual(day["precip_in"]["mean"], 0.01)
        # Los Angeles' climate day is eight hours behind UTC, all year.
        self.assertEqual(sorted(store.latest({"weather": ["KLAX"]}, self.clock())["weather"]["KLAX"]["dates"]),
                         ["2026-09-24", "2026-09-25", "2026-09-26"])
        # Never before it was received, live or on a tape.
        self.assertEqual(store.latest({"weather": ["KNYC"]}, self.clock() - 0.001), {})
        self.assertEqual(store.series({"weather": ["KNYC"]}, self.clock() - 3600, self.clock() - 1, 300), {})
        tape = store.series({"weather": ["KNYC"]}, self.clock() - 3600, self.clock() + 3600, 300)["weather"]["KNYC"]
        self.assertEqual([r["t"] for r in tape], ["2026-09-24T03:30:00.000Z"])

    def test_a_station_is_fetched_again_only_when_a_newer_run_exists(self):
        meteo = Meteo(self.clock)
        store = self.recorder({"weather": ["KNYC"]}, transports={"weather": meteo.transport()})
        store.run()
        self.assertEqual([a[0] for a in meteo.asked], ["meta", "meta", "ensemble"])
        self.clock.advance(899)
        self.assertFalse(store.due())
        self.clock.advance(1)
        self.assertTrue(store.due())
        store.run()  # the same runs: confirmed, not fetched
        self.assertEqual([a[0] for a in meteo.asked], ["meta", "meta", "ensemble", "meta", "meta"])
        entry = store.coverage({"weather": ["KNYC"]})["weather"]["KNYC"]
        self.assertEqual((entry["polls"], entry["ok"], entry["snapshots"]), (2, 2, 1))
        self.assertEqual(store.db.execute("SELECT changed FROM polls WHERE feed = 'weather' ORDER BY finished").fetchall(), [(1,), (0,)])
        # A newer run: fetched, and a new row from the moment it was received.
        meteo.run_at += 6 * 3600
        meteo.shift = 1.5
        self.clock.advance(900)
        store.run()
        self.assertEqual(meteo.asked[-1][0], "ensemble")
        rows = store.series({"weather": ["KNYC"]}, self.clock() - 7200, self.clock(), 60)["weather"]["KNYC"]
        self.assertEqual([r["runs"]["gfs_seamless"]["init"] for r in rows], ["2026-09-23T12:00:00Z", "2026-09-23T18:00:00Z"])
        self.assertEqual(rows[-1]["t"], feeds.stamp(self.clock()))

    def test_a_failed_poll_stores_nothing_and_is_fetched_again(self):
        meteo = Meteo(self.clock)
        routes = meteo.routes()
        routes[ENSEMBLE_HOST + "/v1/ensemble?*"] = TransportError("the host is down")
        store = self.recorder({"weather": ["KNYC"]}, transports={"weather": FakeTransport(routes)})
        out = store.run()
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("weather", "KNYC")])
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)
        self.assertEqual(store.latest({"weather": ["KNYC"]}, self.clock()), {})  # absent: unavailable, never zero
        self.assertEqual(store.db.execute("SELECT ok, error FROM polls").fetchall()[0][0], 0)
        self.assertTrue(all(level == "warning" for level, _ in self.alerts))
        store._fetchers.clear()
        store._transports = {"weather": meteo.transport()}
        self.clock.advance(300)  # a failed key is asked again in five minutes, not at the next quarter hour's check
        self.assertTrue(store.due())
        store.run()
        self.assertEqual(meteo.asked[-1][0], "ensemble")  # the same runs, but its last poll failed: fetched
        self.assertIn("KNYC", store.latest({"weather": ["KNYC"]}, self.clock())["weather"])
        # Open-Meteo's meta.json down: every station's poll fails, and nothing is stored.
        down = FakeTransport(default=TransportError("the host is down"))
        other = FeedRecorder(path=Path(self.dir.name) / "other.sqlite", transports={"weather": down}, clock=self.clock, ledger=None,
                             keys={"weather": ["KNYC", "KLAX"]})
        self.addCleanup(other.close)
        self.assertEqual(sorted(k for _, k, _ in other.run()["failed"]), ["KLAX", "KNYC"])
        self.assertEqual(other.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)

    def test_the_nws_forecast_is_recorded_as_issued_and_unchanged_content_once(self):
        from ltcm.tests.test_data_weather import POINTS, recorded

        transport = FakeTransport({POINTS: recorded("nws_points_knyc.json"),
                                   "https://api.weather.gov/gridpoints/OKX/34,45/forecast": recorded("nws_forecast_knyc.json"),
                                   "https://api.weather.gov/gridpoints/OKX/34,45/forecast/hourly": recorded("nws_hourly_knyc.json")})
        store = self.recorder({"nws": ["KNYC"]}, transports={"nws": transport})
        store.run()
        row = store.latest({"nws": ["KXHIGHNY"]}, self.clock())["nws"]["KNYC"]
        self.assertEqual((row["t"], row["issued"], row["periods"][1]["temperature"]), ("2026-09-24T03:30:00.000Z", "2026-09-23T21:46:15Z", 68.0))
        self.assertLessEqual(epoch(row["issued"]), epoch(row["t"]))
        self.assertNotIn("source", row)
        self.clock.advance(3600)
        store.run()
        entry = store.coverage({"nws": ["KNYC"]})["nws"]["KNYC"]
        self.assertEqual((entry["polls"], entry["ok"], entry["snapshots"]), (2, 2, 1))  # the same forecast: stored once


class ForecastHistory(RecorderCase):
    def setUp(self):
        super().setUp()
        self.clock.set("2026-09-24T17:00:00Z")  # 12:00 EST: today's New York row (stamped 16:00Z) is out
        self.meteo = Meteo(self.clock)

    def test_every_row_is_stamped_by_the_rule_and_never_shown_before(self):
        store = self.recorder({"forecast": ["KNYC"]}, transports={"forecast": self.meteo.transport()}, backfill_pages=10)
        out = store.run()
        self.assertEqual(out["failed"], [])
        stamps = self.stamps(store, "forecast", "KNYC")
        # One row a day at 11:00 New York standard time (16:00Z), never one stamped after now.
        self.assertTrue(all(datetime.fromtimestamp(at, timezone.utc).strftime("%H:%M:%S") == "16:00:00" for at in stamps))
        self.assertEqual(feeds.stamp(stamps[-1]), "2026-09-24T16:00:00.000Z")
        self.assertEqual({b - a for a, b in zip(stamps, stamps[1:])}, {86400.0})
        rows = store.db.execute("SELECT received, started FROM snapshots WHERE feed = 'forecast'").fetchall()
        self.assertTrue(all(started >= received for received, started in rows))  # fetched after, stamped by the rule
        row = store.latest({"forecast": ["KNYC"]}, self.clock())["forecast"]["KNYC"]
        self.assertEqual(row["t"], "2026-09-24T16:00:00.000Z")
        self.assertEqual(row["issued_by"], "2026-09-24T04:00:00.000Z")  # 23:00 EST the evening before
        self.assertEqual({day: v["lead_days"] for day, v in row["dates"].items()}, {"2026-09-24": 1, "2026-09-25": 2, "2026-09-26": 3})
        # Each value is the model's forecast at that lead over the whole climate day (05:00Z to 04:00Z).
        hours = [epoch("2026-09-25T05:00:00Z") + 3600 * i for i in range(24)]
        self.assertEqual(row["dates"]["2026-09-25"]["models"]["ecmwf_ifs025"]["high"], max(Meteo.temperature(h, 2, "ecmwf_ifs025") for h in hours))
        self.assertEqual(row["dates"]["2026-09-26"]["models"]["gfs_seamless"]["low"], min(Meteo.temperature(h, 3, "gfs_seamless") for h in
                                                                                        [epoch("2026-09-26T05:00:00Z") + 3600 * i for i in range(24)]))
        self.assertEqual(row["dates"]["2026-09-24"]["models"]["gfs_seamless"]["precip_in"], round(24 * 0.02, 3))
        # A millisecond before 16:00Z the day before's row is what a wake or a replay step sees.
        before = store.latest({"forecast": ["KNYC"]}, epoch("2026-09-24T15:59:59.999Z"))["forecast"]["KNYC"]
        self.assertEqual((before["t"], sorted(before["dates"])), ("2026-09-23T16:00:00.000Z", ["2026-09-23", "2026-09-24", "2026-09-25"]))
        self.assertNotIn("previous_day0", json.dumps(self.meteo.asked))

    def test_the_backfill_reaches_its_target_and_a_live_pass_asks_only_for_a_new_day(self):
        store = self.recorder({"forecast": ["KNYC"]}, transports={"forecast": self.meteo.transport()}, backfill_pages=2)
        store.run()  # the newest month, then two pages of backfill
        for _ in range(10):
            if not store._backfill_pending():
                break
            self.clock.advance(61)
            store.run()
        self.assertFalse(store._backfill_pending())
        state = store.coverage({"forecast": ["KNYC"]})["forecast"]["KNYC"]
        self.assertTrue(state["backfill"]["complete"], state)
        stamps = self.stamps(store, "forecast", "KNYC")
        target = epoch("2026-09-24T17:00:00Z") - 60 * 86400
        self.assertTrue(0 <= stamps[0] - target < 86400)  # the first row at or after the target: 60 days back
        self.assertEqual({b - a for a, b in zip(stamps, stamps[1:])}, {86400.0})  # no hole
        asked = len(self.meteo.asked)
        self.clock.set("2026-09-25T15:59:00Z")
        store.run()
        self.assertEqual(len(self.meteo.asked), asked)  # the newest row that can exist is held: nothing asked
        self.clock.set("2026-09-25T16:05:00Z")
        store.run()
        self.assertEqual(len(self.meteo.asked), asked + 1)
        self.assertEqual(self.meteo.asked[-1], ("archive", "2026-09-25", "2026-09-28"))
        self.assertEqual(feeds.stamp(self.stamps(store, "forecast", "KNYC")[-1]), "2026-09-25T16:00:00.000Z")
        # Covered over a Kalshi daily strategy's 49 days: the replay gate's 20 day-blocks and more.
        now = self.clock()
        window = store.coverage({"forecast": ["KNYC"]}, now - 49 * 86400, now)["forecast"]["KNYC"]
        self.assertEqual(window["covered_seconds"], 49 * 86400.0)

    def test_the_replay_shows_a_row_only_from_its_stamp(self):
        store = self.recorder({"forecast": ["KNYC"]}, transports={"forecast": self.meteo.transport()}, backfill_pages=10)
        store.run()
        code = '''
from datetime import datetime

NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "t", "symbols": ["BTC/USD"], "bars": {"timeframe": "5Min", "limit": 5},
         "feeds": {"forecast": ["KXHIGHNY"]}}
PARAMS = {}

def decide(ctx):
    row = ((ctx.get("feeds") or {}).get("forecast") or {}).get("KNYC")
    if row is not None and datetime.fromisoformat(row["t"].replace("Z", "+00:00")) > datetime.fromisoformat(ctx["now"].replace("Z", "+00:00")):
        raise ValueError("a forecast from the future")
    seen = list((ctx.get("memory") or {}).get("seen") or [])
    seen.append([ctx["now"], row and row["t"]])
    return {"intents": [], "memory": {"seen": seen}}
'''
        times = ["2026-09-23T15:59:59Z", "2026-09-23T16:00:00Z", "2026-09-24T15:59:59Z", "2026-09-24T16:00:00Z", "2026-09-24T17:00:00Z"]
        wanted = requested({"forecast": ["KXHIGHNY"]})
        self.assertEqual(wanted, {"forecast": ["KNYC"]})
        tape = {"venue": "alpaca", "horizon": "hour", "step_seconds": 1,
                "steps": [{"t": t, "bars": {"BTC/USD": {"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}}} for t in times],
                "feeds": store.series(wanted, "2026-09-23T00:00:00Z", self.clock(), 1)}
        result = run_replay(code, {}, tape, stake=100.0, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["errors"], 0)
        self.assertEqual([seen[1] for seen in result["final_memory"]["seen"]],
                         ["2026-09-22T16:00:00.000Z", "2026-09-23T16:00:00.000Z", "2026-09-23T16:00:00.000Z",
                          "2026-09-24T16:00:00.000Z", "2026-09-24T16:00:00.000Z"])


class WhatIsRecorded(RecorderCase):
    def test_the_stations_follow_the_weather_desk(self):
        desks = niches.load()
        stations = feeds.weather_stations(desks)
        self.assertEqual(len(stations), 20)
        self.assertEqual(stations[:3], ["KLAX", "KMIA", "KNYC"])  # the desk's own order: KXRAIN names none
        self.assertEqual(len(set(stations)), 20)
        self.assertIn("KXRAIN", feeds.weather_unmapped(desks))

    def test_needs_feeds_accept_the_weather_feeds_by_station_series_or_city(self):
        self.assertEqual(requested({"weather": ["KXHIGHNY", "KXLOWTNYC", "nyc", "KXBTCD", "KLAX", "KXHIGHTPHX"],
                                    "nws": ["new york"], "forecast": ["KXLOWTPHIL", "KXRAIN"], "fog": ["KNYC"]}),
                         {"weather": ["KNYC", "KLAX", "KPHX"], "nws": ["KNYC"], "forecast": ["KPHL"]})
        desk = niches.load()["kalshi-weather"]
        out = niches.constrain({"venue": "kalshi", "horizon": "day", "series": ["KXHIGHNY"],
                                "feeds": {"weather": ["KXHIGHNY"], "forecast": ["KNYC"], "perps": ["BTC"]}}, desk)
        self.assertEqual(out["feeds"], {"weather": ["KNYC"], "forecast": ["KNYC"], "perps": ["BTC"]})

    def test_describe_health_and_the_coverage_rows_name_the_host(self):
        meteo = Meteo(self.clock)
        store = self.recorder({"weather": ["KNYC"], "forecast": ["KNYC"]}, transports=meteo.transport(), backfill_pages=10)
        store.run()
        described = store.describe()
        self.assertEqual((described["weather"]["host"], described["forecast"]["host"]),
                         ("ensemble-api.open-meteo.com", "historical-forecast-api.open-meteo.com"))
        self.assertEqual(described["weather"]["recording"], ["KNYC"])
        self.assertIn("receive time", described["weather"]["point_in_time"])
        self.assertIn("11:00 local standard time", described["forecast"]["point_in_time"])
        self.assertEqual(described["forecast"]["replayable_now"], {"hour": ["KNYC"], "day": ["KNYC"]})
        self.assertNotIn("waiting_for", described["weather"])
        health = store.health()
        self.assertEqual((health["weather"]["host"], health["weather"]["recording"]), ("ensemble-api.open-meteo.com", 1))
        rows = {e.payload["feed"]: e.payload for e in self.ledger.iter(kinds="data.coverage")}
        self.assertEqual((rows["weather"]["host"], rows["weather"]["status"], rows["weather"]["asset"]),
                         ("ensemble-api.open-meteo.com", "current", "feed"))
        self.assertEqual(rows["forecast"]["backfill"]["KNYC"]["complete"], True)

    def test_the_weather_recorders_give_way_to_a_live_board(self):
        meteo = Meteo(self.clock)
        store = self.recorder({"weather": ["KNYC", "KLAX"], "sports": ["nfl"]}, transports=meteo.transport())
        store._schedule("sports", "nfl", self.clock() + 10 ** 6)
        store._next[("weather", "KLAX")] = 0.0
        store._schedule("sports", "nfl", 0.0)  # a scoreboard is due: the weather pass waits for it
        self.assertFalse(store._poll_source("weather", "KLAX", {"polled": [], "stored": 0, "failed": []}))
        self.assertEqual(meteo.asked, [])
        self.assertTrue(store.due())

    def test_a_recorder_that_keeps_giving_way_to_live_boards_goes_ahead_once_it_has_waited(self):
        # Sept 25, 2026: with the evening's boards live (each due every 60 s) and a pass longer than that, the `odds`
        # recorder gave way on every pass and asked nothing from 18:48Z to past 21:05Z. It waits STARVE_SECONDS at most.
        meteo = Meteo(self.clock)
        store = self.recorder({"weather": ["KNYC", "KLAX"], "sports": ["nfl"]}, transports=meteo.transport())
        out = {"polled": [], "stored": 0, "failed": []}
        store._next[("weather", "KLAX")] = 0.0
        store._next[("weather", "KNYC")] = 0.0
        store._schedule("sports", "nfl", 0.0)  # a board is due, and stays due: the lane never catches up
        self.assertFalse(store._poll_source("weather", "KLAX", out))
        self.clock.advance(feeds_module.STARVE_SECONDS - 1)
        self.assertFalse(store._poll_source("weather", "KLAX", out), "still inside its wait")
        self.assertEqual(meteo.asked, [])
        self.clock.advance(2)
        self.assertTrue(store._poll_source("weather", "KLAX", out), "waited long enough: it goes ahead of the board")
        self.assertTrue(meteo.asked)
        asked = len(meteo.asked)
        self.assertFalse(store._poll_source("weather", "KNYC", out), "one starved recorder a pass: the next one waits")
        self.assertEqual(len(meteo.asked), asked)
        store._forced_this_pass = False  # a new pass (`run` resets it)
        self.clock.advance(feeds_module.STARVE_SECONDS + 1)
        self.assertTrue(store._poll_source("weather", "KNYC", out))

    def test_requests_for_weather_data_are_answered_once_it_is_recorded(self):
        self.assertEqual({name: request_feed(name) for name in (
            "weather_ensemble_forecasts", "gfs_ecmwf_ensemble_members", "nws_point_forecast", "historical_weather_forecasts",
            "weather_forecast_history_backfill", "live_sports_scores", "weather_station_observations_history")},
            {"weather_ensemble_forecasts": "weather", "gfs_ecmwf_ensemble_members": "weather", "nws_point_forecast": "nws",
             "historical_weather_forecasts": "forecast", "weather_forecast_history_backfill": "forecast",
             "live_sports_scores": "sports", "weather_station_observations_history": "metar"})  # the METARs, Sept 25, 2026
        commons = Commons(self.ledger, clock=self.clock)
        asked = commons.request_tool("mullins-2", "weather_ensemble_forecasts", "the fair value of each bracket I bid on")["queued"]
        store = self.recorder({"weather": ["KNYC"]}, transports=Meteo(self.clock).transport())
        self.assertEqual(store.fulfil_requests(commons), [])
        store.run()
        self.assertEqual(store.fulfil_requests(commons), [asked])
        answer = self.ledger.last("tool.fulfilled").payload["outcome"]
        self.assertIn("NEEDS['feeds'] = {'weather': ['KXHIGHNY']}", answer)
        self.assertIn("ctx['feeds']['weather'][key]", answer)
        self.assertIn("KNYC", answer)


# ---------------------------------------------------------------------------------- earnings
class Edgar:
    """An EDGAR whose company browse feed lists synthetic 8-Ks newest first, paged by start and count
    as the real one is (ltcm/tests/fixtures/feeds/edgar_8k_aapl.atom is its shape)."""

    def __init__(self, filings: dict):
        self.filings = filings  # ticker -> [(acceptance ISO with offset, items, form)], any order
        self.asked: list = []

    def feed(self, method, url, body):
        q = query(url)
        ticker, start, count = q["CIK"], int(q["start"]), int(q["count"])
        self.asked.append((ticker, start, count))
        if ticker not in self.filings:
            return (200, {"content-type": "text/html"}, b"<!DOCTYPE HTML><html><head><title>Company Information: </title></head></html>")
        rows = sorted(self.filings[ticker], key=lambda r: datetime.fromisoformat(r[0]).timestamp(), reverse=True)[start:start + count]
        entries = "".join(
            f"<entry><content type=\"text/xml\"><accession-number>0000000001-26-{i + start:06d}</accession-number>"
            f"<filing-date>{accepted[:10]}</filing-date><filing-href>https://www.sec.gov/Archives/edgar/data/1/{i}/x-index.htm</filing-href>"
            f"<filing-type>{form}</filing-type><items-desc>{items}</items-desc></content><updated>{accepted}</updated></entry>"
            for i, (accepted, items, form) in enumerate(rows))
        body = (f"<?xml version=\"1.0\" ?><feed xmlns=\"http://www.w3.org/2005/Atom\"><company-info><cik>0000320193</cik>"
                f"<conformed-name>{ticker} Inc.</conformed-name></company-info>{entries}<updated>2026-09-24T00:00:00-04:00</updated></feed>")
        return (200, {"content-type": "application/atom+xml"}, body.encode())

    def transport(self) -> FakeTransport:
        from ltcm.data.edgar import BROWSE_URL

        return FakeTransport({BROWSE_URL + "?*": lambda method, url, body: self.feed(method, url, body)})  # a test may swap `feed`


def quarters(first: str, count: int, *, hour: str = "16:30:28-04:00") -> list:
    """`count` earnings 8-Ks a quarter apart from `first`, with a director change between each."""
    day = date.fromisoformat(first)
    out = []
    for i in range(count):
        at = day + timedelta(days=91 * i)
        out.append((f"{at.isoformat()}T{hour}", "items 2.02 and 9.01", "8-K"))
        out.append((f"{(at + timedelta(days=20)).isoformat()}T17:05:00-04:00", "item 5.02", "8-K"))
    return out


class Earnings(RecorderCase):
    def setUp(self):
        super().setUp()
        self.clock.set("2026-09-24T03:30:00Z")

    def test_each_announcement_is_stamped_at_its_acceptance_and_backfilled_two_years(self):
        edgar = Edgar({"AAPL": quarters("2024-01-30", 11)})
        store = self.recorder({"earnings": ["AAPL"]}, transports={"earnings": edgar.transport()}, backfill_pages=10)
        out = store.run()
        self.assertEqual(out["failed"], [])
        stamps = self.stamps(store, "earnings", "AAPL")
        expected = [epoch(f"{(date(2024, 1, 30) + timedelta(days=91 * i)).isoformat()}T20:30:28Z") for i in range(11)]
        target = self.clock() - 740 * 86400
        self.assertEqual(stamps, [at for at in expected if at >= target])  # 2.02 only, each at its acceptance time
        row = store.latest({"earnings": ["AAPL"]}, self.clock())["earnings"]["AAPL"]
        self.assertEqual((row["t"], row["accepted"], row["items"], row["form"]), (feeds.stamp(expected[-1]), "2026-07-28T20:30:28Z",
                                                                                   ["2.02", "9.01"], "8-K"))
        self.assertEqual(row["previous"], [feeds.stamp(at) for at in expected[-5:-1]][::-1])  # the four before it, newest first
        # Never before its acceptance, live or in a replay.
        before = store.latest({"earnings": ["AAPL"]}, expected[-1] - 0.001)["earnings"]["AAPL"]
        self.assertEqual(before["t"], feeds.stamp(expected[-2]))
        tape = store.series({"earnings": ["AAPL"]}, expected[-3] + 1, expected[-1] - 1, 3600)["earnings"]["AAPL"]
        self.assertEqual([r["t"] for r in tape], [feeds.stamp(expected[-3]), feeds.stamp(expected[-2])])
        # The searched span counts as covered: an Alpaca daily window has its 20 day-blocks at once.
        window = store.coverage({"earnings": ["AAPL"]}, self.clock() - 126 * 86400, self.clock())["earnings"]["AAPL"]
        self.assertEqual(window["covered_seconds"], 126 * 86400.0)
        self.assertTrue(window["backfill"]["complete"])

    def test_a_live_pass_reads_back_only_a_day_before_its_last_poll_and_adds_a_new_filing(self):
        filings = quarters("2025-10-30", 4)
        edgar = Edgar({"AAPL": filings})
        store = self.recorder({"earnings": ["AAPL"]}, transports={"earnings": edgar.transport()}, backfill_pages=10)
        store.run()
        asked = len(edgar.asked)
        self.clock.advance(600)
        self.assertTrue(store.due())
        store.run()
        self.assertEqual(edgar.asked[asked:], [("AAPL", 0, 40)])  # one page: a day before the last poll is on it
        self.clock.advance(600)  # 03:50Z
        filings.append(("2026-09-23T23:46:00-04:00", "items 2.02 and 9.01", "8-K"))  # accepted four minutes ago
        filings.append(("2026-09-23T23:59:00-04:00", "items 2.02 and 9.01", "8-K"))  # "accepted" after now: never stored
        store.run()
        row = store.latest({"earnings": ["AAPL"]}, self.clock())["earnings"]["AAPL"]
        self.assertEqual(row["t"], "2026-09-24T03:46:00.000Z")
        self.assertEqual(self.stamps(store, "earnings", "AAPL")[-1], epoch("2026-09-24T03:46:00Z"))
        self.assertEqual(store.latest({"earnings": ["AAPL"]}, epoch("2026-09-24T03:45:59Z"))["earnings"]["AAPL"]["accepted"],
                         "2026-07-30T20:30:28Z")

    def test_a_ticker_edgar_does_not_know_is_not_listed_and_a_filer_without_8ks_has_no_rows(self):
        edgar = Edgar({"VALE": []})  # a foreign issuer files 6-Ks; this EDGAR knows no HOOD at all
        store = self.recorder({"earnings": ["HOOD", "VALE"]}, transports={"earnings": edgar.transport()}, backfill_pages=10)
        out = store.run()
        self.assertEqual([(k, feeds.NOT_LISTED in e) for _, k, e in out["failed"]], [("HOOD", True)])
        self.assertFalse(store.coverage({"earnings": ["HOOD"]})["earnings"]["HOOD"]["backfill"]["pending"])  # unavailable, not waiting
        self.assertEqual(store.latest({"earnings": ["HOOD", "VALE"]}, self.clock()), {})
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)

    def test_a_listing_too_long_to_read_fails_rather_than_claim_the_span(self):
        edgar = Edgar({"JPM": [(f"2026-09-{1 + i // 20:02d}T{10 + i % 12:02d}:00:00-04:00", "item 8.01", "8-K") for i in range(400)]})
        store = self.recorder({"earnings": ["JPM"]}, transports={"earnings": edgar.transport()}, backfill_pages=10)
        out = store.run()
        self.assertTrue(out["failed"] and "was not read to its end" in out["failed"][0][2], out["failed"])
        entry = store.coverage({"earnings": ["JPM"]}, self.clock() - 86400 * 30, self.clock())["earnings"]["JPM"]
        self.assertEqual(entry["covered_seconds"], 0.0)

    def test_the_next_date_is_recorded_at_receipt_and_a_page_without_one_is_not_a_failure(self):
        from ltcm.data.nasdaq import HOST
        from ltcm.tests.test_data_nasdaq import recorded

        pages = {"AAPL": recorded(), "HOOD": {"data": {"announcement": "", "reportText": "No earnings data is available."}}}
        transport = FakeTransport({f"{HOST}/api/analyst/*": lambda m, url, b: pages[url.split("/")[-2]]})
        store = self.recorder({"earnings_date": ["AAPL", "HOOD"]}, transports={"earnings_date": transport})
        out = store.run()
        self.assertEqual([(k, feeds.NOT_LISTED in e) for _, k, e in out["failed"]], [("HOOD", True)])
        row = store.latest({"earnings_date": ["AAPL", "HOOD"]}, self.clock())["earnings_date"]
        self.assertEqual(sorted(row), ["AAPL"])
        self.assertEqual((row["AAPL"]["t"], row["AAPL"]["date"], row["AAPL"]["estimated"]), ("2026-09-24T03:30:00.000Z", "2026-10-29", True))
        self.assertEqual(store.latest({"earnings_date": ["AAPL"]}, self.clock() - 0.001), {})
        self.assertEqual(store.health()["earnings_date"]["failing"], ["HOOD"])  # said, but scheduled like a success
        self.clock.advance(6 * 3600)
        store.run()
        self.assertEqual(store.coverage({"earnings_date": ["AAPL"]})["earnings_date"]["AAPL"]["snapshots"], 1)  # unchanged: once

    def test_a_history_pass_gives_way_to_a_live_board_and_resumes_where_it_stopped(self):
        edgar = Edgar({"AAPL": quarters("2025-10-30", 4), "MSFT": quarters("2025-10-29", 4), "NVDA": quarters("2025-11-19", 4)})
        store = self.recorder({"earnings": ["AAPL", "MSFT", "NVDA"], "sports": ["nfl"]}, transports={"earnings": edgar.transport()},
                              backfill_pages=0)
        store._schedule("sports", "nfl", self.clock() + 10 ** 6)  # not due: the first pass runs through
        store._poll_history("earnings", {"polled": [], "stored": 0, "failed": []})
        self.assertEqual(sorted({t for t, _, _ in edgar.asked}), ["AAPL", "MSFT", "NVDA"])
        # A scoreboard falls due while the next pass is on its first stock: the pass stops there.
        feed = edgar.feed

        def answer(method, url, body):
            store._schedule("sports", "nfl", 0.0)
            return feed(method, url, body)

        edgar.feed = answer
        self.clock.advance(600)
        asked = len(edgar.asked)
        store._poll_history("earnings", {"polled": [], "stored": 0, "failed": []})
        self.assertEqual([t for t, _, _ in edgar.asked[asked:]], ["AAPL"])
        self.assertTrue(store.due())  # due again at once, behind the board
        edgar.feed = feed
        store._schedule("sports", "nfl", self.clock() + 10 ** 6)  # the board has been polled
        self.clock.advance(30)
        asked = len(edgar.asked)
        store._poll_history("earnings", {"polled": [], "stored": 0, "failed": []})
        self.assertEqual([t for t, _, _ in edgar.asked[asked:]], ["MSFT", "NVDA"])  # on from where it stopped, AAPL not asked twice

    # -- EDGAR's slow answers (Sept 24, 2026) -------------------------------------------------------------
    @staticmethod
    def slow_edgar(filings: dict, slow: dict) -> Edgar:
        """An EDGAR whose browse feed times out for the stocks in `slow` (ticker -> timeouts left; -1:
        every time), the way it did 31 times in 995 polls on Sept 24, 2026."""
        edgar = Edgar(filings)
        feed = edgar.feed

        def answer(method, url, body):
            ticker = query(url)["CIK"]
            left = slow.get(ticker, 0)
            if left:
                slow[ticker] = left - 1 if left > 0 else left
                raise TransportError(f"GET {url} failed: The read operation timed out")
            return feed(method, url, body)

        edgar.feed = answer
        return edgar

    def earnings_warnings(self):
        return [text for _, text in self.alerts if "earnings polls failed" in text]

    def test_one_slow_answer_is_read_at_the_next_poll_and_not_warned(self):
        """Sept 24, 2026: the hourly warning named every timed-out stock ("3 of 24 earnings polls failed
        (NFLX: TransportError: GET https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=NFLX&
        type=8-K&dateb=&owner=include&st...") though each was read at its next poll, 29 of 30 at once."""
        filings = {"AAPL": quarters("2025-10-30", 4), "NFLX": quarters("2025-10-16", 4)}
        edgar = self.slow_edgar(filings, {"NFLX": 1})
        store = self.recorder({"earnings": ["AAPL", "NFLX"]}, transports={"earnings": edgar.transport()}, backfill_pages=10)
        out = store.run()
        self.assertEqual([key for feed, key, _ in out["failed"] if feed == "earnings"], ["NFLX"])  # the pass saw it fail
        self.assertEqual(self.earnings_warnings(), [])  # and the next request read it: nothing to tell
        self.clock.advance(600)
        store.run()
        self.assertEqual(store.latest({"earnings": ["NFLX"]}, self.clock())["earnings"]["NFLX"]["accepted"], "2026-07-16T20:30:28Z")
        self.assertEqual(self.earnings_warnings(), [])

    def test_a_stock_that_keeps_failing_is_warned_with_its_reason_not_its_query(self):
        filings = {"AAPL": quarters("2025-10-30", 4), "NFLX": quarters("2025-10-16", 4)}
        edgar = self.slow_edgar(filings, {"NFLX": -1})
        store = self.recorder({"earnings": ["AAPL", "NFLX"]}, transports={"earnings": edgar.transport()}, backfill_pages=10)
        store.run()  # the live poll and the backfill page: two failures in a row
        self.assertEqual(self.earnings_warnings(), [])
        self.assertEqual(store.health()["earnings"]["failing"], ["NFLX"])  # health says it at once
        self.clock.advance(feeds.RETRY_SECONDS)
        store.run()  # the third
        warned = self.earnings_warnings()
        self.assertEqual(len(warned), 1, self.alerts)
        self.assertIn("feeds: 1 of 2 earnings polls failed 3 times in a row (NFLX: TransportError: GET "
                      "https://www.sec.gov/cgi-bin/browse-edgar failed: The read operation timed out)", warned[0])
        self.assertNotIn("AAPL", warned[0])

    def test_edgar_is_given_forty_five_seconds_to_answer(self):
        """Sept 24, 2026: 18 of 964 good polls answered after 20-29 s, and 31 hit the 30 s timeout."""
        from ltcm.data.edgar import BROWSE_URL

        edgar = Edgar({"AAPL": quarters("2025-10-30", 4)})

        class Timed(FakeTransport):
            timeouts: list = []

            def get(self, url, headers=None, timeout=None):
                self.timeouts.append(timeout)
                return super().get(url, headers=headers, timeout=timeout)

        transport = Timed({BROWSE_URL + "?*": lambda method, url, body: edgar.feed(method, url, body)})
        store = self.recorder({"earnings": ["AAPL"]}, transports={"earnings": transport}, backfill_pages=10)
        self.assertEqual(store.run()["failed"], [])
        self.assertEqual(set(transport.timeouts), {45.0})

    def test_needs_and_requests_for_earnings(self):
        self.assertEqual(requested({"earnings": ["aapl", "SPY", "BTC/USD", "VALE"], "earnings_date": ["HOOD", "XYZ"]}),
                         {"earnings": ["AAPL", "VALE"], "earnings_date": ["HOOD"]})
        self.assertEqual({name: request_feed(name) for name in (
            "point_in_time_earnings_calendar", "megacap_earnings_calendar", "point_in_time_earnings_surprise_panel",
            "point_in_time_earnings_calendar_and_surp", "forward_earnings_event_feed", "earnings_announcement_times_history",
            "point_in_time_earnings_dates_for_the_16_")},
            {"point_in_time_earnings_calendar": "earnings_date", "megacap_earnings_calendar": "earnings_date",
             "point_in_time_earnings_surprise_panel": None, "point_in_time_earnings_calendar_and_surp": None,
             "forward_earnings_event_feed": "earnings_date", "earnings_announcement_times_history": "earnings",
             "point_in_time_earnings_dates_for_the_16_": "earnings_date"})


# ------------------------------------------------------------------------------------- rates
class Rates(RecorderCase):
    def test_one_request_answers_every_rate_each_stamped_at_receipt(self):
        from ltcm.data.rates import REFERENCE_URL
        from ltcm.tests.test_data_rates import recorded_rates

        answer = recorded_rates()
        answer["refRates"] = [row for row in answer["refRates"] if row["type"] != "TGCR"]  # one rate missing today
        transport = FakeTransport({REFERENCE_URL: answer})
        store = self.recorder({"rates": ["SOFR", "EFFR", "TGCR"]}, transports={"rates": transport})
        out = store.run()
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(out["polled"], ["rates"])
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("rates", "TGCR")])  # that one fails; the others stand
        rows = store.latest({"rates": ["sofr", "EFFR", "TGCR"]}, self.clock())["rates"]
        self.assertEqual(sorted(rows), ["EFFR", "SOFR"])
        self.assertEqual((rows["SOFR"]["t"], rows["SOFR"]["effective_date"], rows["SOFR"]["rate"]), ("2026-09-24T03:30:00.000Z", "2026-09-22", 3.87))
        self.assertEqual(store.latest({"rates": ["SOFR"]}, self.clock() - 0.001), {})
        self.clock.advance(1800)
        store.run()
        self.assertEqual(store.coverage({"rates": ["SOFR"]})["rates"]["SOFR"]["snapshots"], 1)  # the same rate: stored once

    def test_the_newest_curve_by_tenor_and_last_months_at_a_months_start(self):
        from ltcm.data.rates import PAR_YIELD_URL
        from ltcm.tests.test_data_rates import recorded_curve

        empty = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        transport = FakeTransport({PAR_YIELD_URL + "?*": lambda m, url, b: (200, {}, recorded_curve() if url.endswith("202609") else empty)})
        store = self.recorder({"treasury": ["2Y", "10Y"]}, transports={"treasury": transport})
        store.run()
        rows = store.latest({"treasury": ["10y", "2-year", "11Y"]}, self.clock())["treasury"]
        self.assertEqual(rows["10Y"], {"tenor": "10Y", "date": "2026-09-23", "yield": 5.11, "t": "2026-09-24T03:30:00.000Z"})
        self.assertEqual(rows["2Y"]["yield"], 4.85)
        self.clock.set("2026-10-01T03:30:00Z")  # October's first curve is not out: the newest is September's
        store.run()
        self.assertEqual(store.latest({"treasury": ["10Y"]}, self.clock())["treasury"]["10Y"]["date"], "2026-09-23")
        self.assertEqual([c["query"]["field_tdr_date_value_month"] for c in transport.calls], ["202609", "202610", "202609"])

    def test_requests_for_rates(self):
        self.assertEqual({name: request_feed(name) for name in ("sofr_daily_fixings", "treasury_par_yield_curve", "fed_funds_effective_rate",
                                                                "ust_10y_yield_history", "rates_desk_macro_calendar")},
                         {"sofr_daily_fixings": "rates", "treasury_par_yield_curve": "treasury", "fed_funds_effective_rate": "rates",
                          "ust_10y_yield_history": None, "rates_desk_macro_calendar": None})
        self.assertEqual(requested({"rates": ["sofr", "LIBOR"], "treasury": ["10 years", "DGS10"]}), {"rates": ["SOFR"], "treasury": ["10Y"]})


# ---------------------------------------------------------------------------------- sports odds
def board(*games) -> dict:
    """An NFL scoreboard (the site API's shape, ltcm/tests/test_data_sports.py) of (id, start, state)."""
    return {"events": [{"id": gid, "name": f"Away {gid} at Home {gid}", "date": start, "competitions": [{
        "competitors": [{"homeAway": "home", "score": "0", "team": {"displayName": f"Home {gid}"}},
                        {"homeAway": "away", "score": "0", "team": {"displayName": f"Away {gid}"}}],
        "status": {"type": {"state": state}}}]} for gid, start, state in games]}


class Odds(RecorderCase):
    def transport(self, **over):
        from ltcm.data.sports import CORE_HOST
        from ltcm.tests.test_data_sports import NFL, core

        routes = {NFL: board(("401872948", "2026-09-24T20:00Z", "pre"), ("401872949", "2026-09-24T01:00Z", "in"),
                             ("401872950", "2026-09-27T17:00Z", "pre")),
                  CORE_HOST + "/v2/sports/football/leagues/nfl/events/401872948/competitions/401872948/odds": core("espn_core_odds_401872948.json"),
                  CORE_HOST + "/v2/sports/football/leagues/nfl/events/401872948/competitions/401872948/predictor":
                      core("espn_core_predictor_401872948.json")}
        routes.update(over)
        return FakeTransport(routes)

    def test_the_lines_of_the_boards_coming_games_are_recorded_at_receipt(self):
        fake = self.transport()
        store = self.recorder({"sports": ["nfl"], "odds": ["nfl"]}, transports=fake)
        out = store.run()
        self.assertEqual(out["polled"], ["sports:nfl", "odds:nfl"])  # the board first, then its lines
        self.assertEqual(out["failed"], [])
        row = store.latest({"odds": ["KXNFLGAME"]}, self.clock())["odds"]["nfl"]
        self.assertEqual(row["t"], "2026-09-24T03:30:00.000Z")
        # Only the game that has not started and starts within 36 hours: not the one on now, not Sunday's.
        self.assertEqual([e["id"] for e in row["events"]], ["401872948"])
        game = row["events"][0]
        self.assertEqual((game["home"], game["lines"][0]["home_ml"], game["lines"][0]["implied_home"], game["win_probability"]["home"]),
                         ("Home 401872948", -245, 0.6806, 0.74465))
        self.assertEqual(store.latest({"odds": ["nfl"]}, self.clock() - 0.001), {})
        self.assertFalse(any("401872950" in c["url"] or "401872949" in c["url"] for c in fake.calls))

    def test_a_league_without_a_board_is_not_listed_and_a_failed_line_fails_the_league(self):
        from ltcm.data.sports import CORE_HOST

        store = self.recorder({"odds": ["nfl"]}, transports=self.transport())
        out = store.run()
        self.assertEqual([(k, feeds.NOT_LISTED in e) for _, k, e in out["failed"]], [("nfl", True)])  # no board recorded: waits
        broken = self.transport(**{CORE_HOST + "/v2/sports/football/leagues/nfl/events/401872948/competitions/401872948/odds":
                                   TransportError("the host is down")})
        other = FeedRecorder(path=Path(self.dir.name) / "other.sqlite", transports=broken, clock=self.clock, ledger=None,
                             keys={"sports": ["nfl"], "odds": ["nfl"]})
        self.addCleanup(other.close)
        out = other.run()
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("odds", "nfl")])
        self.assertEqual(other.latest({"odds": ["nfl"]}, self.clock()), {})  # never a partial board
        self.assertEqual({name: request_feed(name) for name in ("nfl_sportsbook_odds", "live_win_probability_nfl",
                                                                "resolved_sports_moneyline_price_outcome_", "live_sports_scores",
                                                                "sports_moneyline_inseason_replay_tape")},
                         {"nfl_sportsbook_odds": "odds", "live_win_probability_nfl": "odds",
                          "resolved_sports_moneyline_price_outcome_": None, "live_sports_scores": "sports",
                          "sports_moneyline_inseason_replay_tape": None})  # a Kalshi tape, asked by name on Sept 23


class OddsCadence(RecorderCase):
    """Sept 25, 2026 (K1): one pass a league every 30 minutes, at most 16 games, left most of a
    college-football Saturday (60-110 games within 36 hours) without lines. Each game is now refreshed
    on its own cadence -- every 30 minutes inside 6 hours of its start, every 2 hours before -- by a
    pass every 5 minutes of at most 20 games, while the league's row lists every coming game with its
    last lines and when they were fetched."""

    START = epoch("2026-09-24T03:30:00Z")

    def slate(self, near=3, far=22):
        """An NFL board of `near` games starting within 6 hours and `far` starting 6 to 36 hours out."""
        games = [(f"5000{i:02d}", self.START + 3600 * (1 + i), "pre") for i in range(near)]
        games += [(f"6000{i:02d}", self.START + 3600 * (7 + i), "pre") for i in range(far)]
        return board(*[(gid, datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), state) for gid, at, state in games])

    def transport(self, slate, failing=()):
        from ltcm.data.sports import CORE_HOST
        from ltcm.tests.test_data_sports import NFL, core

        lines, predictor = core("espn_core_odds_401872948.json"), core("espn_core_predictor_401872948.json")

        def answer(method, url, body):
            game = url.split("/events/")[1].split("/")[0]
            if game in failing:
                raise TransportError("the host is down")
            return predictor if url.endswith("/predictor") else lines

        return FakeTransport({NFL: slate, CORE_HOST + "/v2/sports/football/leagues/nfl/events/*": answer})

    def fetched(self, fake):
        return [c["url"].split("/events/")[1].split("/")[0] for c in fake.calls if c["url"].endswith("/odds")]

    def row(self, store):
        return store.latest({"odds": ["nfl"]}, self.clock())["odds"]["nfl"]

    def test_a_pass_is_bounded_and_every_game_is_listed_with_when_its_lines_were_fetched(self):
        fake = self.transport(self.slate())
        store = self.recorder({"sports": ["nfl"], "odds": ["nfl"]}, transports=fake)
        store.run()
        self.assertEqual(len(self.fetched(fake)), feeds.SportsOdds.MAX_FETCHES)  # 20 of 25, soonest first
        self.assertEqual(self.fetched(fake)[:4], ["500000", "500001", "500002", "600000"])
        row = self.row(store)
        self.assertEqual(len(row["events"]), 25)
        waiting = [e for e in row["events"] if e["fetched"] is None]
        self.assertEqual(([e["id"] for e in waiting], {len(e["lines"]) for e in waiting}),
                         (["600017", "600018", "600019", "600020", "600021"], {0}))
        for event in row["events"]:  # never a line fetched after the row's own stamp
            self.assertTrue(event["fetched"] is None or epoch(event["fetched"]) <= epoch(row["t"]))
        self.clock.advance(300)
        store.run()
        self.assertEqual(self.fetched(fake)[20:], ["600017", "600018", "600019", "600020", "600021"])  # the rest, next pass
        self.assertTrue(all(e["fetched"] for e in self.row(store)["events"]))
        stored = len(self.stamps(store, "odds", "nfl"))
        self.clock.advance(300)
        store.run()  # nothing due: nothing fetched, and the unchanged row is not stored again
        self.assertEqual((len(self.fetched(fake)), len(self.stamps(store, "odds", "nfl"))), (25, stored))
        self.clock.advance(1800 - 600 + 1)  # 30 minutes after the first pass: the games inside 6 hours are due
        store.run()
        self.assertEqual(self.fetched(fake)[25:], ["500000", "500001", "500002"])
        self.clock.advance(7200 - 1800)  # 2 hours: the games further out are due again too
        store.run()
        again = self.fetched(fake)[28:]
        # Two games have started and are listed no more; the two now inside 6 hours fell due longest ago
        # (30 minutes after the first pass), then the third near game, then the far games fetched first.
        self.assertEqual(again, ["600000", "600001", "500002"] + [f"6000{i:02d}" for i in range(2, 17)])
        self.assertNotIn("500000", [e["id"] for e in self.row(store)["events"]])

    def test_a_game_whose_refresh_fails_keeps_its_last_lines_and_a_pass_that_all_fails_stores_nothing(self):
        failing: set = set()
        fake = self.transport(self.slate(near=2, far=0), failing=failing)
        store = self.recorder({"sports": ["nfl"], "odds": ["nfl"]}, transports=fake)
        store.run()
        first = {e["id"]: e["fetched"] for e in self.row(store)["events"]}
        failing.add("500000")
        self.clock.advance(1801)
        out = store.run()
        self.assertEqual(out["failed"], [])
        now = {e["id"]: e["fetched"] for e in self.row(store)["events"]}
        self.assertEqual(now["500000"], first["500000"])  # its last lines, with their own fetch time
        self.assertGreater(epoch(now["500001"]), epoch(first["500001"]))
        failing.add("500001")
        stored = len(self.stamps(store, "odds", "nfl"))
        self.clock.advance(1801)
        out = store.run()
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("odds", "nfl")])
        self.assertEqual(len(self.stamps(store, "odds", "nfl")), stored)

    def test_a_restarted_house_goes_on_from_the_leagues_last_row(self):
        fake = self.transport(self.slate(near=2, far=0))
        store = self.recorder({"sports": ["nfl"], "odds": ["nfl"]}, transports=fake)
        store.run()
        store.close()
        self.clock.advance(600)
        again = FeedRecorder(path=Path(self.dir.name) / "feeds.sqlite", transports=fake, clock=self.clock, ledger=None,
                             keys={"sports": ["nfl"], "odds": ["nfl"]}, sleep=no_sleep)
        self.addCleanup(again.close)
        again.run()
        self.assertEqual(len(self.fetched(fake)), 2)  # nothing due yet: the lines held are the last row's
        self.assertTrue(all(e["fetched"] for e in self.row(again)["events"]))


# ------------------------------------------------------------------------------------ attention
class Attention(RecorderCase):
    def transport(self):
        from ltcm.data.attention import RCP_APPROVAL_URL, TSA_URL
        from ltcm.tests.test_data_attention import rcp_wall, tsa_page

        return FakeTransport({TSA_URL: (200, {"content-type": "text/html"}, tsa_page()),
                              RCP_APPROVAL_URL: (403, {"content-type": "application/json"}, rcp_wall())})

    def test_tsa_is_recorded_at_receipt_and_a_bot_wall_is_blocked_never_a_number(self):
        store = self.recorder({"tsa": ["checkpoint"], "polls": ["trump_approval"]}, transports=self.transport())
        out = store.run()
        row = store.latest({"tsa": ["KXTSAW"], "polls": ["KXTRUMPAPPROVE"]}, self.clock())
        self.assertEqual(sorted(row), ["tsa"])  # the approval average is absent: unavailable, never a number
        self.assertEqual((row["tsa"]["checkpoint"]["t"], row["tsa"]["checkpoint"]["latest"]), ("2026-09-24T03:30:00.000Z",
                                                                                            {"date": "2026-09-22", "travelers": 2077346}))
        self.assertEqual(len(row["tsa"]["checkpoint"]["days"]), 14)
        self.assertEqual(store.latest({"tsa": ["checkpoint"]}, self.clock() - 0.001), {})
        blocked = [e for f, k, e in out["failed"] if f == "polls"]
        self.assertTrue(blocked and feeds.BLOCKED in blocked[0] and "DataDome" in blocked[0], out["failed"])
        self.assertEqual(self.alerts, [])  # a bot wall is said in health, not warned about every hour
        self.assertEqual(store.health()["polls"]["failing"], ["trump_approval"])
        self.assertEqual(store.describe()["polls"]["failing_now"], ["trump_approval"])
        self.assertIn("DataDome", store.coverage({"polls": ["trump_approval"]})["polls"]["trump_approval"]["last_error"])
        self.clock.advance(3600)
        self.assertEqual([k for f, k in store._plan() if f == "polls" and store._next.get((f, k), 0) <= self.clock()], [])  # asked every six hours
        self.assertEqual({name: request_feed(name) for name in ("tsa_checkpoint_volumes", "attention_underlying_value_feed",
                                                                "trump_approval_polling_average", "rotten_tomatoes_point_in_time_feed")},
                         {"tsa_checkpoint_volumes": "tsa", "attention_underlying_value_feed": None,
                          "trump_approval_polling_average": "polls", "rotten_tomatoes_point_in_time_feed": None})

    def test_the_attention_recorders_follow_the_desk(self):
        desks = niches.load()
        store = FeedRecorder(path=Path(self.dir.name) / "desks.sqlite", clock=self.clock, niches=desks)
        self.addCleanup(store.close)
        self.assertEqual((store.keys("tsa"), store.keys("polls")), (["checkpoint"], ["trump_approval"]))


# ------------------------------------------------------------------------------ open interest
class OkxOi:
    """OKX's open-interest history for BTC and ETH from `since`, answered newest first a page at a
    time with `end` exclusive, as recorded on Sept 24, 2026; the hour still running moves with the clock."""

    def __init__(self, clock, since="2026-09-01T00:00:00Z"):
        self.clock, self.since = clock, epoch(since)
        self.asked: list = []

    @staticmethod
    def usd(start: float) -> float:
        return 2.4e9 + (int(start) // 3600 % 50) * 1e6

    def answer(self, method, url, body):
        q = query(url)
        coin = q["instId"].split("-")[0]
        if coin not in ("BTC", "ETH"):
            return {"code": "51001", "data": [], "msg": "Instrument ID doesn't exist."}
        self.asked.append(q.get("end"))
        now = self.clock()
        top = math.floor(now / 3600) * 3600  # the running hour's start
        if "end" in q:
            top = min(top, math.ceil(int(q["end"]) / 1000 / 3600) * 3600 - 3600)
        rows, at = [], top
        while at >= self.since and len(rows) < int(q.get("limit") or 100):
            usd = self.usd(at) + (now - at if at + 3600 > now else 0)  # the running hour's value keeps moving
            rows.append([str(int(at * 1000)), "100", "1", str(usd)])
            at -= 3600
        return {"code": "0", "data": rows, "msg": ""}

    def transport(self) -> FakeTransport:
        from ltcm.data.derivs import OKX_HOST

        return FakeTransport({OKX_HOST + "/api/v5/rubik/stat/contracts/open-interest-history": self.answer})


class OpenInterest(RecorderCase):
    def test_an_hour_is_stored_only_once_it_has_ended_and_stamped_then(self):
        okx = OkxOi(self.clock)
        store = self.recorder({"oi": ["BTC", "DOGE"]}, transports={"oi": okx.transport()}, backfill_pages=40)
        out = store.run()
        self.assertEqual([(k, "51001" in e) for _, k, e in out["failed"]], [("DOGE", True)])  # not listed: absent, not waited for
        stamps = self.stamps(store, "oi", "BTC")
        self.assertEqual(feeds.stamp(stamps[-1]), "2026-09-24T03:00:00.000Z")  # the 02:00 hour, closed; 03:00's is still running
        self.assertEqual(feeds.stamp(stamps[0]), "2026-09-01T01:00:00.000Z")  # OKX's history ends here: the backfill stops
        self.assertEqual({b - a for a, b in zip(stamps, stamps[1:])}, {3600.0})
        row = store.latest({"oi": ["btc"]}, self.clock())["oi"]["BTC"]
        self.assertEqual((row["t"], row["oi_usd"], row["hours"]), ("2026-09-24T03:00:00.000Z", OkxOi.usd(epoch("2026-09-24T02:00:00Z")), 1))
        day_before = OkxOi.usd(epoch("2026-09-23T02:00:00Z"))
        self.assertEqual(row["change_24h_pct"], round((row["oi_usd"] - day_before) / day_before * 100, 4))
        self.assertEqual(store.latest({"oi": ["BTC"]}, epoch("2026-09-24T02:59:59.999Z"))["oi"]["BTC"]["t"], "2026-09-24T02:00:00.000Z")
        state = store.coverage({"oi": ["BTC"]})["oi"]["BTC"]["backfill"]
        self.assertTrue(state["complete"] and state["exhausted"], state)
        self.clock.set("2026-09-24T04:02:30Z")
        store.run()
        self.assertEqual(feeds.stamp(self.stamps(store, "oi", "BTC")[-1]), "2026-09-24T04:00:00.000Z")
        self.assertEqual({name: request_feed(name) for name in ("perp_open_interest_history", "kalshi_open_interest_history",
                                                                "perpetual_open_interest")},
                         {"perp_open_interest_history": "oi", "kalshi_open_interest_history": None, "perpetual_open_interest": "perps"})

    def test_a_backfill_page_does_not_make_the_hourly_pass_skip_the_key(self):
        """Review of #234 (Sept 24, 2026): the hourly pass skipped every key polled in the last five
        minutes -- meant for the keys a pass that gave way had already polled -- and a backfill page
        counts as a poll, so while a key's history was still being paged its newest hour waited a
        whole hour more for the next pass (a new 8-K the same way, for the earnings feed)."""
        okx = OkxOi(self.clock, since="2026-06-01T00:00:00Z")  # a long history: the backfill takes many passes
        store = self.recorder({"oi": ["BTC"]}, transports={"oi": okx.transport()}, backfill_pages=1)
        store.run()  # 03:30: the head and one backfill page
        self.clock.set("2026-09-24T04:01:10Z")
        store.run()  # a backfill pass: one more page of BTC's history
        self.clock.set("2026-09-24T04:02:40Z")
        store.run()  # the hourly pass, due at 04:02:30
        self.assertEqual(feeds.stamp(self.stamps(store, "oi", "BTC")[-1]), "2026-09-24T04:00:00.000Z")
        self.assertFalse(store.coverage({"oi": ["BTC"]})["oi"]["BTC"]["backfill"]["complete"], "the backfill is still running")


# ---------------------------------------------------------------------------- the owner's keys
class Keyed(RecorderCase):
    """EIA's and The Odds API's recorders go live with no code change once the owner places a key and
    allows the host; until then they wait -- poll nothing, and are never said to fail."""

    KEY = "eia-" + "7" * 36

    def transport(self):
        from ltcm.data.eia import HOST
        from ltcm.tests.test_data_keyed import WTI

        return FakeTransport({HOST + "/v2/petroleum/pri/spt/data/?*": WTI})

    def test_off_without_the_key_or_the_host_and_on_with_both(self):
        fake = self.transport()
        waiting = self.recorder({"eia": ["WTI"]}, transports={"eia": fake}, environ={}, allowed_hosts=["api.eia.gov"])
        self.assertEqual((waiting.keys("eia"), waiting.due(), waiting.run()["polled"]), ([], False, []))
        self.assertEqual(fake.calls, [])
        self.assertIn("waiting for the owner's key: EIA_API_KEY", waiting.describe()["eia"]["waiting_for"])
        self.assertIn("EIA_API_KEY", waiting.health()["eia"]["waiting_for"])
        self.assertEqual(waiting.health()["eia"]["failing"], [])  # waiting is not failing
        self.assertEqual([e.payload["feed"] for e in self.ledger.iter(kinds="data.coverage")], [])
        no_host = FeedRecorder(path=Path(self.dir.name) / "no-host.sqlite", transports={"eia": fake}, clock=self.clock,
                               keys={"eia": ["WTI"]}, environ={"EIA_API_KEY": self.KEY}, allowed_hosts=["api.open-meteo.com"])
        self.addCleanup(no_host.close)
        self.assertEqual(no_host.keys("eia"), [])
        self.assertIn("hosts --add api.eia.gov", no_host.waiting_for("eia"))
        live = FeedRecorder(path=Path(self.dir.name) / "live.sqlite", transports={"eia": fake}, clock=self.clock, ledger=self.ledger,
                            keys={"eia": ["WTI"]}, environ={"EIA_API_KEY": self.KEY}, allowed_hosts=["api.eia.gov"])
        self.addCleanup(live.close)
        self.assertIsNone(live.waiting_for("eia"))
        live.run()
        row = live.latest({"eia": ["KXWTI"]}, self.clock())["eia"]["WTI"]
        self.assertEqual((row["t"], row["value"], row["period"]), ("2026-09-24T03:30:00.000Z", 71.05, "2026-09-22"))
        self.assertEqual(fake.calls[-1]["query"]["api_key"], self.KEY)

    def test_the_owners_key_is_never_stored_nor_said(self):
        down = FakeTransport(default=TransportError(f"GET https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={self.KEY} failed: timed out"))
        store = self.recorder({"eia": ["WTI"]}, transports={"eia": down}, environ={"EIA_API_KEY": self.KEY}, allowed_hosts=["api.eia.gov"])
        out = store.run()
        self.assertTrue(out["failed"])
        text = json.dumps([out["failed"], self.alerts, store.health(), store.describe()["eia"],
                           store.db.execute("SELECT * FROM polls").fetchall()])
        self.assertNotIn(self.KEY, text)
        self.assertIn("api_key=***", text)

    def test_the_repository_records_the_keyed_hosts_as_not_yet_allowed(self):
        hosts = feeds.league_hosts()
        self.assertIn("ensemble-api.open-meteo.com", hosts)
        self.assertIn("www.sec.gov", hosts)
        self.assertNotIn("api.eia.gov", hosts)
        self.assertNotIn("api.the-odds-api.com", hosts)
        for name, source in feeds.RECORDERS.items():
            self.assertIn(source.host, hosts + ("api.eia.gov", "api.the-odds-api.com"), name)  # every recorder reads a host on record
        store = FeedRecorder(path=Path(self.dir.name) / "defaults.sqlite", clock=self.clock, environ={"ODDS_API_KEY": "x" * 32})
        self.addCleanup(store.close)
        self.assertIn("hosts --add api.the-odds-api.com", store.waiting_for("consensus"))

    def test_the_consensus_recorder_reads_the_odds_api_per_league(self):
        from ltcm.data.oddsapi import HOST
        from ltcm.tests.test_data_keyed import GAMES

        fake = FakeTransport({HOST + "/v4/sports/americanfootball_nfl/odds?*": GAMES})
        store = self.recorder({"consensus": ["nfl"]}, transports={"consensus": fake}, environ={"ODDS_API_KEY": "o" * 32},
                              allowed_hosts=["api.the-odds-api.com"])
        store.run()
        row = store.latest({"consensus": ["KXNFLGAME"]}, self.clock())["consensus"]["nfl"]
        self.assertEqual((row["league"], row["events"][0]["books"], row["t"]), ("nfl", 2, "2026-09-24T03:30:00.000Z"))
        self.assertEqual(request_feed("consensus_win_probabilities_sports"), "consensus")


# ------------------------------------------------------------------------------ in the House
FORECAST_READER = '''
from datetime import datetime

NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "forecast-reader", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5, "feeds": {"forecast": ["KXHIGHNY"]}}
PARAMS = {}


def decide(ctx):
    memory = dict(ctx.get("memory") or {})
    row = ((ctx.get("feeds") or {}).get("forecast") or {}).get("KNYC")
    if row is not None:
        if datetime.fromisoformat(row["t"].replace("Z", "+00:00")) > datetime.fromisoformat(ctx["now"].replace("Z", "+00:00")):
            raise ValueError("a forecast from the future")
        memory["seen"] = int(memory.get("seen") or 0) + 1
    return {"intents": [], "memory": memory}
'''


class InTheHouse(HouseCase):
    def test_a_strategy_declaring_the_forecast_history_replays_once_the_backfill_is_in(self):
        self.clock.now = epoch("2026-09-24T17:00:00Z")
        recorder = FeedRecorder(self.house, Path(self.dir.name) / "feeds.sqlite", Meteo(self.clock).transport(),
                                keys={"forecast": ["KNYC"]}, sleep=no_sleep, backfill_pages=10)
        self.house.feeds = recorder
        self.addCleanup(recorder.close)
        agent = self.house.spawn("reader", "test-family", FORECAST_READER, reason="test")
        self.assertEqual(agent.needs["feeds"], {"forecast": ["KNYC"]})
        with self.assertRaises(ValueError) as caught:
            self.house._run_replay(agent, agent.code, agent.needs, agent.params)
        self.assertTrue(str(caught.exception).startswith("unsupported input: feeds being backfilled: forecast KNYC"), str(caught.exception))
        self.assertEqual(self.house._replay_own(agent), {"agent": agent.id, "skipped": "waiting for recorded feeds"})
        self.assertEqual(recorder.run()["failed"], [])
        key, tape = self.house.tape_for(agent.needs)
        self.assertTrue(key.endswith(':feeds:{"forecast":["KNYC"]}:ready'), key)
        result = run_replay(agent.code, {}, tape, stake=200.0, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["errors"], 0)  # never a forecast from the future
        self.assertGreater(result["final_memory"]["seen"], 0)
        # A live wake is handed the newest row stamped by now.
        seated = self.seated(name="live-reader", code=FORECAST_READER)
        ctx = self.house.snapshot(seated, self.house.book_of(seated))
        self.assertEqual(ctx["feeds"]["forecast"]["KNYC"]["t"], "2026-09-24T16:00:00.000Z")
        described = self.house.research_capabilities(seated)["observations"]
        self.assertEqual(described["replayable_history"]["forecast"]["replayable_now"], {"hour": ["KNYC"], "day": ["KNYC"]})

    def test_a_kalshi_weather_tape_carries_the_ensemble_and_its_key_names_it(self):
        recorder = FeedRecorder(self.house, Path(self.dir.name) / "feeds.sqlite", Meteo(self.clock).transport(), keys={"weather": ["KNYC"]})
        self.house.feeds = recorder
        self.addCleanup(recorder.close)
        recorder.run()

        class Kalshi:
            def tape(self, series, **kw):
                return {"venue": "kalshi", "horizon": kw["horizon"], "step_seconds": kw["step_seconds"], "steps": [], "results": {}}

        self.house.kalshi_data = Kalshi()
        needs = niches.constrain({"venue": "kalshi", "horizon": "day", "style": "w", "series": ["KXHIGHNY"],
                                  "feeds": {"weather": ["KXHIGHNY", "KXLOWTPHIL"]}}, niches.load()["kalshi-weather"])
        self.assertEqual(needs["feeds"], {"weather": ["KNYC", "KPHL"]})
        key, tape = self.house.tape_for(needs)
        self.assertTrue(key.endswith(':feeds:{"weather":["KNYC","KPHL"]}:short'), key)  # recorded live: twenty days to wait
        self.assertEqual(list(tape["feeds"]["weather"]), ["KNYC"])  # nothing recorded for Philadelphia: absent
        with self.assertRaises(ValueError) as caught:
            self.house._require_feeds(needs, needs["feeds"], tape["feeds_coverage"])
        self.assertTrue(str(caught.exception).startswith("unsupported input: feeds not recorded: weather KPHL"), str(caught.exception))
        self.assertIn("the House records weather KNYC", str(caught.exception))
        self.assertNotIn("perps", str(caught.exception))  # only what these NEEDS declare, not every key of every feed


if __name__ == "__main__":
    unittest.main()
