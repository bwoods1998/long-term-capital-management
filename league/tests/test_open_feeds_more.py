"""The third group of the Kalshi-scale run's recorders (Sept 25, 2026, workstream I2): the White House's
presidential actions and the Federal Register's presidential documents as backfilled point-in-time
history, the NWS's raw climate reports stamped at issue, and EIA's fuel tables, BLS's and BEA's release
calendars and Nasdaq's trade halts recorded live.

Held to the three rules of league/feeds.py -- visible only from the moment it became knowable, live and
in replay; a failed poll stores nothing; unchanged content stored once -- and to each stamp: a post's
publication time, a day's issue at 09:00 New York time, a product's issue time, the House's receive time.
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from league import feeds  # first: league.feeds imports league.open_feeds and registers its recorders
from league.feeds import FeedRecorder, request_feed, requested
from league.ledger import Ledger
from ltcm.data.calendars import BEA_SCHEDULE_URL, BLS_ICS_URL
from ltcm.data.cli_text import FILES, HOST as TGFTP
from ltcm.data.fuel import HOST as EIA, SERIES
from ltcm.data.notices import FEDERAL_REGISTER_URL, HALTS_URL, WHITEHOUSE_FEED_URL
from ltcm.tests import test_data_calendars as calendar_fixtures
from ltcm.tests import test_data_cli_text as cli_fixtures
from ltcm.tests import test_data_fuel as fuel_fixtures
from ltcm.tests import test_data_notices as notice_fixtures
from ltcm.tests.fakes import Clock, FakeTransport, TransportError

NEW_YORK = ZoneInfo("America/New_York")


def epoch(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class RecorderCase(unittest.TestCase):
    START = "2026-09-25T07:30:00Z"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(self.START)
        self.alerts = []
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)

    def recorder(self, keys, transports=None, **kw) -> FeedRecorder:
        kw.setdefault("sleep", lambda seconds: None)
        recorder = FeedRecorder(path=Path(self.dir.name) / "feeds.sqlite", transports=transports, clock=self.clock, ledger=self.ledger,
                                alert=lambda level, text: self.alerts.append((level, text)), keys=keys, **kw)
        self.addCleanup(recorder.close)
        return recorder

    def stamps(self, store, feed, key) -> list:
        return [at for (at,) in store.db.execute("SELECT received FROM snapshots WHERE feed = ? AND key = ? ORDER BY received", (feed, key))]


# ------------------------------------------------------------------------ presidential actions
class Presidential(RecorderCase):
    def transport(self):
        return FakeTransport({WHITEHOUSE_FEED_URL: notice_fixtures.actions_page(1), WHITEHOUSE_FEED_URL + "?paged=2": notice_fixtures.actions_page(2),
                              WHITEHOUSE_FEED_URL + "?paged=3": (404, {}, b"<html>not found</html>")})

    def test_each_action_is_stamped_at_its_post_and_counted_in_its_new_york_day(self):
        transport = self.transport()
        store = self.recorder({"presidential": ["actions", "executive_orders"]}, transports={"presidential": transport}, backfill_pages=10)
        out = store.run()
        self.assertEqual(out["failed"], [])
        stamps = self.stamps(store, "presidential", "actions")
        self.assertEqual(feeds.stamp(stamps[-1]), "2026-09-18T22:02:43.000Z")
        floor = self.clock() - (feeds.BACKFILL_DAYS + 1) * 86400.0  # the replay window and a day for today_et
        from ltcm.data.notices import parse_actions

        posted = [i["published_at"] for page in (1, 2) for i in parse_actions(notice_fixtures.actions_page(page)) if i["published_at"] >= floor]
        self.assertEqual(stamps, sorted(set(posted)))  # both pages, down to the floor and no further
        self.assertGreater(len(posted), len(set(posted)))  # some actions share their second: one row holds them all
        shared = next(at for at in posted if posted.count(at) > 1)
        held = store.latest({"presidential": ["actions"]}, shared)["presidential"]["actions"]
        self.assertEqual((held["count"], len(held["actions"])), (posted.count(shared), posted.count(shared)))
        self.assertLess(min(i["published_at"] for i in parse_actions(notice_fixtures.actions_page(2))), floor)
        self.assertEqual(sum(1 for c in transport.calls if c["url"] == WHITEHOUSE_FEED_URL), 1)  # one read serves every key
        row = store.latest({"presidential": ["KXTRUMPACT"]}, epoch("2026-09-17T21:31:50Z"))["presidential"]["actions"]
        self.assertEqual((row["t"], row["count"], row["actions"][0]["kind"]), ("2026-09-17T21:31:50.000Z", 1, "executive_orders"))
        items = [i for i in parse_actions(notice_fixtures.actions_page(1))
                 if datetime.fromtimestamp(i["published_at"], NEW_YORK).date().isoformat() == "2026-09-17"
                 and i["published_at"] <= epoch("2026-09-17T21:31:50Z")]
        self.assertEqual(row["today_et"], len(items))
        self.assertGreaterEqual(row["today_et"], 3)
        orders = store.latest({"presidential": ["eo"]}, self.clock())["presidential"]["executive_orders"]
        self.assertEqual((orders["t"], orders["actions"][0]["kind"]), ("2026-09-18T22:02:43.000Z", "executive_orders"))
        before = store.latest({"presidential": ["actions"]}, epoch("2026-09-18T22:02:42.999Z"))["presidential"]["actions"]
        self.assertEqual(before["t"], "2026-09-18T21:42:13.000Z")  # never shown before it was posted
        state = store.coverage({"presidential": ["actions"]})["presidential"]["actions"]["backfill"]
        self.assertTrue(state["complete"], state)

    def test_a_failed_feed_stores_nothing(self):
        down = FakeTransport(default=TransportError("GET https://www.whitehouse.gov/presidential-actions/feed/ failed: timed out"))
        store = self.recorder({"presidential": ["actions"]}, transports={"presidential": down})
        out = store.run()
        self.assertTrue(out["failed"])
        self.assertEqual(self.stamps(store, "presidential", "actions"), [])


# ------------------------------------------------------------------------ the Federal Register
class FederalRegister(RecorderCase):
    def transport(self):
        last_page = {**notice_fixtures.documents(), "next_page_url": None, "results": []}
        return FakeTransport({FEDERAL_REGISTER_URL: notice_fixtures.documents(),
                              "https://www.federalregister.gov/api/v1/documents?*": last_page})

    def test_a_days_issue_is_one_row_stamped_at_nine_new_york_time(self):
        transport = self.transport()
        store = self.recorder({"federal_register": ["documents", "executive_orders"]}, transports={"federal_register": transport})
        out = store.run()
        self.assertEqual(out["failed"], [])
        row = store.latest({"federal_register": ["documents"]}, self.clock())["federal_register"]["documents"]
        self.assertEqual((row["t"], row["date"], row["count"]), ("2026-09-23T13:00:00.000Z", "2026-09-23", 2))  # 09:00 EDT
        orders = store.latest({"federal_register": ["executive_orders"]}, self.clock())["federal_register"]["executive_orders"]
        self.assertEqual((orders["count"], orders["documents"][0]["executive_order_number"]), (1, "14431"))
        self.assertEqual(store.latest({"federal_register": ["documents"]}, epoch("2026-09-23T12:59:59Z"))["federal_register"]["documents"]["date"],
                         "2026-09-22")
        self.assertEqual(len([c for c in transport.calls if c["url"].startswith(FEDERAL_REGISTER_URL)]), 1)  # both keys and the backfill, one read
        state = store.coverage({"federal_register": ["documents"]})["federal_register"]["documents"]["backfill"]
        self.assertTrue(state["complete"], state)


# ------------------------------------------------------------------------------- EIA's tables
class Fuel(RecorderCase):
    def test_each_series_at_receipt_once_and_a_failure_stores_nothing(self):
        transport = FakeTransport({EIA + SERIES["GASOLINE"][0]: fuel_fixtures.gasoline(), EIA + SERIES["WTI"][0]: fuel_fixtures.wti(),
                                   EIA + SERIES["DIESEL"][0]: (500, {}, b"<html>error</html>")})
        store = self.recorder({"fuel": ["GASOLINE", "WTI", "DIESEL"]}, transports={"fuel": transport})
        out = store.run()
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("fuel", "DIESEL")])
        rows = store.latest({"fuel": ["gas", "KXWTI", "diesel"]}, self.clock())["fuel"]
        self.assertEqual(sorted(rows), ["GASOLINE", "WTI"])
        self.assertEqual((rows["GASOLINE"]["t"], rows["GASOLINE"]["latest"]), ("2026-09-25T07:30:00.000Z", {"date": "2026-09-21", "value": 4.478}))
        self.assertEqual(store.latest({"fuel": ["WTI"]}, self.clock() - 0.001), {})
        self.clock.advance(6 * 3600)
        store.run()
        self.assertEqual(store.coverage({"fuel": ["WTI"]})["fuel"]["WTI"]["snapshots"], 1)


# ------------------------------------------------------------------------- the NWS's CLI text
class ClimateText(RecorderCase):
    def transport(self, **files):
        return FakeTransport({f"{TGFTP}/data/raw/cd/{FILES[station]}.txt": body for station, body in files.items()})

    def test_a_report_is_stamped_at_its_issue_and_the_backfill_asks_nothing(self):
        transport = self.transport(KNYC=cli_fixtures.product("KNYC"), KDEN=cli_fixtures.product("KDEN"))
        store = self.recorder({"cli_text": ["KNYC", "KDEN"]}, transports={"cli_text": transport}, backfill_pages=10)
        out = store.run()
        self.assertEqual(out["failed"], [])
        self.assertEqual(len(transport.calls), 2)  # one read a station; the NWS keeps nothing older to backfill
        nyc = store.latest({"cli_text": ["KXHIGHNY"]}, self.clock())["cli_text"]["KNYC"]
        self.assertEqual((nyc["t"], nyc["date"], nyc["high"], nyc["final"], nyc["preliminary"]),
                         ("2026-09-25T06:33:00.000Z", "2026-09-24", 66.0, True, False))
        denver = store.latest({"cli_text": ["KDEN"]}, self.clock())["cli_text"]["KDEN"]
        self.assertEqual((denver["t"], denver["final"], denver["preliminary"]), ("2026-09-24T23:30:00.000Z", False, True))
        self.assertEqual(store.latest({"cli_text": ["KNYC"]}, epoch("2026-09-25T06:32:59Z")), {})
        self.assertTrue(store.coverage({"cli_text": ["KNYC"]})["cli_text"]["KNYC"]["backfill"]["exhausted"])
        self.clock.advance(600)
        store.run()
        self.assertEqual(len(self.stamps(store, "cli_text", "KNYC")), 1)  # the same product: not stored again

    def test_a_station_without_a_file_is_not_declared_and_a_failure_stores_nothing(self):
        self.assertEqual(requested({"cli_text": ["KXHIGHTNOLA", "KNYC"]}), {"cli_text": ["KNYC"]})
        store = self.recorder({"cli_text": ["KNYC"]}, transports={"cli_text": self.transport(KNYC=(503, {}, b"busy"))})
        out = store.run()
        self.assertTrue(out["failed"])
        self.assertEqual(self.stamps(store, "cli_text", "KNYC"), [])


# ------------------------------------------------------------------------- release calendars
class Releases(RecorderCase):
    def test_the_next_release_of_each_key_at_receipt(self):
        transport = FakeTransport({BLS_ICS_URL: calendar_fixtures.bls(), BEA_SCHEDULE_URL: calendar_fixtures.bea()})
        store = self.recorder({"bls_releases": ["cpi", "jobs", "all"], "bea_releases": ["gdp", "pce"]}, transports=transport)
        out = store.run()
        self.assertEqual(out["failed"], [])
        self.assertEqual(sum(1 for c in transport.calls if c["url"] == BLS_ICS_URL), 1)  # one read for every key
        cpi = store.latest({"bls_releases": ["KXCPI"]}, self.clock())["bls_releases"]["cpi"]
        self.assertEqual((cpi["t"], cpi["next"]["at"], cpi["next"]["release"]), ("2026-09-25T07:30:00.000Z", "2026-10-14T12:30:00Z",
                                                                                 "Consumer Price Index"))
        gdp = store.latest({"bea_releases": ["KXGDP"]}, self.clock())["bea_releases"]["gdp"]
        self.assertEqual(gdp["next"]["at"], "2026-09-30T12:30:00Z")
        self.assertTrue(all(row["date"] <= "2026-11-24" for row in cpi["upcoming"]))
        self.clock.advance(12 * 3600)
        store.run()
        self.assertEqual(store.coverage({"bea_releases": ["gdp"]})["bea_releases"]["gdp"]["snapshots"], 1)


# ------------------------------------------------------------------------------- trade halts
class Halts(RecorderCase):
    def test_one_read_answers_every_stock_and_all(self):
        transport = FakeTransport({HALTS_URL: notice_fixtures.halts()})
        store = self.recorder({"halts": ["AAPL", "all"]}, transports={"halts": transport})
        store.run()
        self.assertEqual(len(transport.calls), 1)
        rows = store.latest({"halts": ["AAPL", "all"]}, self.clock())["halts"]
        self.assertEqual((rows["AAPL"]["count"], rows["AAPL"]["halts"]), (0, []))  # not halted: a row, never absent
        self.assertEqual((rows["all"]["count"], rows["all"]["t"]), (17, "2026-09-25T07:30:00.000Z"))
        self.clock.advance(300)
        store.run()
        self.assertEqual(store.coverage({"halts": ["all"]})["halts"]["all"]["snapshots"], 1)
        down = self.recorder({"halts": ["all"]}, transports={"halts": FakeTransport(default=TransportError("GET x failed: reset"))})
        self.assertTrue(down.run()["failed"])


# ------------------------------------------------------------------------------ vocabulary
class WhatIsDeclared(RecorderCase):
    def test_needs_accept_the_new_keys(self):
        self.assertEqual(requested({"presidential": ["KXTRUMPACT", "eo", "vetoes"], "federal_register": ["proclamation"],
                                    "fuel": ["KXWTI", "gas", "AAA"], "bls_releases": ["KXPAYROLLS"], "bea_releases": ["KXGDP"],
                                    "halts": ["all", "ZZZZ"]}),
                         {"presidential": ["actions", "executive_orders"], "federal_register": ["proclamations"],
                          "fuel": ["WTI", "GASOLINE"], "bls_releases": ["jobs"], "bea_releases": ["gdp"], "halts": ["all"]})

    def test_requests_name_them_without_taking_what_others_answer(self):
        self.assertEqual({name: request_feed(name) for name in (
            "white_house_presidential_actions", "executive_orders_feed", "federal_register_documents", "fuel_prices_weekly",
            "cli_raw_text_product", "bls_release_calendar", "cpi_release_schedule", "gdp_release_dates", "trading_halts_feed",
            "rates_desk_macro_calendar", "cpi_history", "cpi_release_values", "weather_station_observations_history",
            "trump_approval_polling_average", "fomc_meeting_calendar")},
            {"white_house_presidential_actions": "presidential", "executive_orders_feed": "presidential",
             "federal_register_documents": "federal_register", "fuel_prices_weekly": "fuel", "cli_raw_text_product": "cli_text",
             "bls_release_calendar": "bls_releases", "cpi_release_schedule": "bls_releases", "gdp_release_dates": "bea_releases",
             "trading_halts_feed": "halts", "rates_desk_macro_calendar": None, "cpi_history": None, "cpi_release_values": "bls",
             "weather_station_observations_history": "metar", "trump_approval_polling_average": "polls",
             "fomc_meeting_calendar": "fomc"})

    def test_every_host_is_on_record(self):
        from league import open_feeds_more

        hosts = feeds.league_hosts()
        for source in open_feeds_more.SOURCES:
            self.assertIn(source.host, hosts, source.name)
            self.assertIs(feeds.RECORDERS[source.name], source)
        self.assertIn("presidential", feeds.HISTORY_FEEDS)
        self.assertNotIn("halts", feeds.HISTORY_FEEDS)


if __name__ == "__main__":
    unittest.main()
