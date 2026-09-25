"""The macro recorders of the Kalshi-scale run (Sept 25, 2026, workstream I2): BLS's series, FiscalData,
the ECB's reference rates, the CFTC's Commitments of Traders and the Fed's calendar -- each held to the
three rules of league/feeds.py and to its own stamp (the House's receive time for BLS, FiscalData and
the calendar; 17:00 Frankfurt time for an ECB fixing; seven days after its as-of Tuesday for a CFTC
report, or its receipt when it appears later than that)."""

import copy
import json
import re
import tempfile
import unittest
import urllib.parse
from datetime import datetime
from pathlib import Path

from league import feeds  # first: league.feeds imports league.open_feeds and registers its recorders
from league.feeds import FeedRecorder, request_feed, requested
from league.ledger import Ledger
from ltcm.data.fx import DAILY_URL, HIST_90D_URL
from ltcm.data.releases import AUCTIONS_URL, BLS_V1_URL, COT_URL, DEBT_URL, DTS_CASH_URL, FED_CALENDAR_URL
from ltcm.tests import test_data_fx as fx_fixtures
from ltcm.tests import test_data_releases as fixtures
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


# ----------------------------------------------------------------------------------------- BLS
class Bls(RecorderCase):
    def test_one_query_answers_every_series_stamped_at_receipt_and_stored_once(self):
        transport = FakeTransport({("POST", BLS_V1_URL): fixtures.bls()})
        store = self.recorder({"bls": ["CPI", "CPI_NSA", "PAYROLLS", "UNRATE"]}, transports={"bls": transport})
        out = store.run()
        self.assertEqual((out["failed"], out["polled"], len(transport.calls)), ([], ["bls"], 1))
        rows = store.latest({"bls": ["KXCPIYOY", "KXPAYROLLS"]}, self.clock())["bls"]
        self.assertEqual((rows["CPI_NSA"]["t"], rows["CPI_NSA"]["series_id"], rows["CPI_NSA"]["latest"]["period"]),
                         ("2026-09-25T06:40:00.000Z", "CUUR0000SA0", "2026-08"))
        self.assertIsNotNone(rows["CPI_NSA"]["change_12m_pct"])
        self.assertTrue(rows["PAYROLLS"]["latest"]["preliminary"])
        self.assertEqual(store.latest({"bls": ["CPI"]}, self.clock() - 0.001), {})
        self.clock.advance(5400)
        store.run()
        self.assertEqual((len(transport.calls), store.coverage({"bls": ["CPI"]})["bls"]["CPI"]["snapshots"]), (2, 1))

    def test_a_spent_daily_quota_is_blocked_and_asked_again_at_the_cadence_not_every_five_minutes(self):
        spent = {"status": "REQUEST_NOT_PROCESSED", "message": ["Request could not be serviced, as the daily threshold for total number "
                                                                "of requests allocated to the user has been reached."]}
        transport = FakeTransport({("POST", BLS_V1_URL): spent})
        store = self.recorder({"bls": ["CPI", "UNRATE"]}, transports={"bls": transport})
        out = store.run()
        self.assertTrue(out["failed"] and all(feeds.BLOCKED in error for _, _, error in out["failed"]), out["failed"])
        self.assertEqual(self.alerts, [])
        self.assertEqual(store.latest({"bls": ["CPI"]}, self.clock()), {})
        self.assertEqual(store._next[("bls", "*")], self.clock() + 5400)
        self.assertEqual(store.health()["bls"]["failing"], ["CPI", "UNRATE"])

    def test_a_failed_query_stores_nothing(self):
        down = FakeTransport({("POST", BLS_V1_URL): TransportError("POST https://api.bls.gov/publicAPI/v1/timeseries/data/ failed: timed out")})
        store = self.recorder({"bls": ["CPI"]}, transports={"bls": down})
        out = store.run()
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("bls", "CPI")])
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)


# ---------------------------------------------------------------------------------- FiscalData
class Fiscal(RecorderCase):
    def test_each_dataset_is_its_own_key_and_one_that_fails_leaves_the_others(self):
        transport = FakeTransport({DTS_CASH_URL: fixtures.tga(), AUCTIONS_URL: fixtures.auctions(),
                                   DEBT_URL: TransportError("GET https://api.fiscaldata.treasury.gov/... failed: timed out")})
        store = self.recorder({"fiscal": ["tga", "debt", "auctions"]}, transports={"fiscal": transport})
        out = store.run()
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("fiscal", "debt")])
        rows = store.latest({"fiscal": ["TGA", "Treasury auctions", "debt"]}, self.clock())["fiscal"]
        self.assertEqual(sorted(rows), ["auctions", "tga"])
        self.assertEqual((rows["tga"]["t"], rows["tga"]["closing"]), ("2026-09-25T06:40:00.000Z", 947317.0))
        self.assertEqual([a["term"] for a in rows["auctions"]["upcoming"]], ["26-Week", "52-Week", "6-Week"])
        self.assertEqual(rows["auctions"]["recent"][0]["auction_date"], "2026-09-24")


# ----------------------------------------------------------------------------------------- ECB
def daily_file(day: str, usd: float) -> bytes:
    body = fx_fixtures.daily().decode("utf-8").replace("2026-09-24", day)
    return re.sub(r"currency='USD' rate='[0-9.]+'", f"currency='USD' rate='{usd}'", body).encode("utf-8")


class Fx(RecorderCase):
    def transport(self, daily=None):
        return FakeTransport({HIST_90D_URL: (200, {"last-modified": fx_fixtures.MODIFIED}, fx_fixtures.last_90_days()),
                              DAILY_URL: daily or (200, {"last-modified": fx_fixtures.MODIFIED}, fx_fixtures.daily())})

    def test_each_fixing_is_stamped_at_17_frankfurt_and_the_history_is_backfilled(self):
        transport = self.transport()
        store = self.recorder({"fx": ["USD", "JPY"]}, transports={"fx": transport})
        out = store.run()
        self.assertEqual(out["failed"], [])
        row = store.latest({"fx": ["KXEURUSD", "USDJPY"]}, self.clock())["fx"]
        self.assertEqual((row["USD"]["t"], row["USD"]["date"], row["USD"]["per_eur"], row["USD"]["per_usd"]),
                         ("2026-09-24T15:00:00.000Z", "2026-09-24", 1.1367, None))  # 17:00 CEST; the file changed at 13:56Z
        self.assertEqual(row["JPY"]["per_usd"], round(180.57 / 1.1367, 6))
        self.assertIsNotNone(row["USD"]["change_1d_pct"])
        self.assertIsNotNone(row["USD"]["change_5d_pct"])
        before = store.latest({"fx": ["USD"]}, epoch("2026-09-24T14:59:59Z"))["fx"]["USD"]
        self.assertEqual(before["date"], "2026-09-23")
        stamps = self.stamps(store, "fx", "USD")
        self.assertLessEqual(stamps[0], self.clock() - 83 * 86400.0 + 5 * 86400.0)  # 75 days and the lookback, from the 90-day file
        self.assertTrue(store.coverage({"fx": ["USD"]})["fx"]["USD"]["backfill"]["complete"])
        self.assertEqual([c["url"] for c in transport.calls].count(HIST_90D_URL), 1)  # one file for both currencies

    def test_the_daily_file_adds_the_next_fixing_only_once_its_stamp_has_passed(self):
        store = self.recorder({"fx": ["USD"]}, transports={"fx": self.transport()})
        store.run()
        late = daily_file("2026-09-25", 1.1401)
        transport = FakeTransport({DAILY_URL: (200, {"last-modified": "Fri, 25 Sep 2026 15:30:00 GMT"}, late),
                                   HIST_90D_URL: (500, {}, b"")})
        store._fetchers.pop("fx")
        store._transports = {"fx": transport}
        self.clock.set("2026-09-25T14:20:00Z")  # published, but its 17:00 CEST stamp has not passed
        store.run()
        self.assertEqual(feeds.stamp(self.stamps(store, "fx", "USD")[-1]), "2026-09-24T15:00:00.000Z")
        self.clock.set("2026-09-25T16:20:00Z")
        store.run()
        row = store.latest({"fx": ["USD"]}, self.clock())["fx"]["USD"]
        self.assertEqual((row["t"], row["per_eur"]), ("2026-09-25T15:30:00.000Z", 1.1401))  # published late: stamped when it changed
        self.assertEqual({c["url"] for c in transport.calls}, {DAILY_URL})
        self.assertEqual(row["change_1d_pct"], round((1.1401 / 1.1367 - 1) * 100, 4))

    def test_an_unknown_currency_is_not_listed(self):
        store = self.recorder({"fx": ["XXX"]}, transports={"fx": self.transport()})
        out = store.run()
        self.assertTrue(out["failed"] and feeds.NOT_LISTED in out["failed"][0][2], out["failed"])


# ---------------------------------------------------------------------------------------- CFTC
class Cot(RecorderCase):
    def transport(self, extra=()):
        reports = fixtures.cot() + list(extra)

        def answer(method, url, body):
            where = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["$where"][0]
            code = re.search(r"cftc_contract_market_code='([^']+)'", where).group(1)
            since = re.search(r">= '([0-9-]+)'", where)
            until = re.search(r"< '([0-9-]+)'", where)
            rows = [r for r in reports if r["cftc_contract_market_code"] == code
                    and (since is None or r["report_date_as_yyyy_mm_dd"][:10] >= since.group(1))
                    and (until is None or r["report_date_as_yyyy_mm_dd"][:10] < until.group(1))]
            return sorted(rows, key=lambda r: r["report_date_as_yyyy_mm_dd"], reverse=True)

        return FakeTransport({COT_URL: answer})

    @staticmethod
    def report(as_of: str, long: int) -> dict:
        row = copy.deepcopy([r for r in fixtures.cot() if r["cftc_contract_market_code"] == "133741"][0])
        row.update(report_date_as_yyyy_mm_dd=f"{as_of}T00:00:00.000", noncomm_positions_long_all=str(long))
        return row

    def test_each_report_is_stamped_a_week_after_its_as_of_and_backfilled(self):
        store = self.recorder({"cot": ["BTC", "ES"]}, transports={"cot": self.transport()})
        out = store.run()
        self.assertEqual(out["failed"], [])
        self.assertEqual([feeds.stamp(at) for at in self.stamps(store, "cot", "BTC")],
                         ["2026-09-15T00:00:00.000Z", "2026-09-22T00:00:00.000Z"])
        row = store.latest({"cot": ["bitcoin"]}, self.clock())["cot"]["BTC"]
        self.assertEqual((row["as_of"], row["noncommercial"]["net"]), ("2026-09-15", 16744.0 - 14276.0))
        self.assertEqual(row["net_change_1w"], (16744.0 - 14276.0) - (17600.0 - 16076.0))
        self.assertEqual(store.latest({"cot": ["BTC"]}, epoch("2026-09-21T23:59:59Z"))["cot"]["BTC"]["as_of"], "2026-09-08")
        self.assertTrue(store.coverage({"cot": ["BTC"]})["cot"]["BTC"]["backfill"]["complete"])

    def test_a_report_waits_for_its_stamp_and_one_seen_late_is_stamped_at_receipt(self):
        store = self.recorder({"cot": ["BTC"]}, transports={"cot": self.transport()})
        store.run()
        released = self.transport([self.report("2026-09-22", 17000)])
        store._fetchers.pop("cot")
        store._transports = {"cot": released}
        self.clock.set("2026-09-26T12:00:00Z")  # released Friday; its stamp is Tuesday 00:00Z
        store.run()
        self.assertEqual(feeds.stamp(self.stamps(store, "cot", "BTC")[-1]), "2026-09-22T00:00:00.000Z")
        self.clock.set("2026-09-29T00:15:00Z")
        store.run()
        self.assertEqual(feeds.stamp(self.stamps(store, "cot", "BTC")[-1]), "2026-09-29T00:00:00.000Z")
        late = self.transport([self.report("2026-09-22", 17000), self.report("2026-09-29", 18000)])
        store._fetchers.pop("cot")
        store._transports = {"cot": late}
        self.clock.set("2026-10-08T09:00:00Z")  # the Sept 29 report first seen two days after its stamp
        store.run()
        self.assertEqual(feeds.stamp(self.stamps(store, "cot", "BTC")[-1]), "2026-10-08T09:00:00.000Z")


# ------------------------------------------------------------------------------------ the Fed
class Fed(RecorderCase):
    def test_one_request_answers_every_kind_and_a_failure_stores_nothing(self):
        transport = FakeTransport({FED_CALENDAR_URL: (200, {}, fixtures.calendar())})
        store = self.recorder({"fomc": ["fomc", "speeches", "testimony", "beige"]}, transports={"fomc": transport})
        out = store.run()
        self.assertEqual((out["failed"], len(transport.calls)), ([], 1))
        row = store.latest({"fomc": ["KXFED"]}, self.clock())["fomc"]["fomc"]
        self.assertEqual((row["t"], row["next"]["title"], row["next_meeting"]["date"], row["next_meeting"]["end_date"]),
                         ("2026-09-25T06:40:00.000Z", "FOMC Minutes", "2026-10-28", "2026-10-28"))
        self.clock.advance(12 * 3600)
        store.run()
        self.assertEqual(store.coverage({"fomc": ["fomc"]})["fomc"]["fomc"]["snapshots"], 1)

    def test_a_calendar_that_fails_is_a_failed_poll(self):
        store = self.recorder({"fomc": ["fomc", "beige"]}, transports={"fomc": FakeTransport({FED_CALENDAR_URL: (503, {}, b"")})})
        out = store.run()
        self.assertEqual(sorted(k for f, k, _ in out["failed"]), ["beige", "fomc"])
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)


# ------------------------------------------------------------------------------ the vocabulary
class WhatIsDeclared(unittest.TestCase):
    def test_needs_accept_the_macro_feeds_by_their_own_names_and_kalshis(self):
        self.assertEqual(requested({"bls": ["KXCPI", "cpi_nsa", "CES0000000001", "KXU3", "GDP"],
                                    "fx": ["KXEURUSD", "USDJPY", "gbp", "EURCHF", "XXX"], "cot": ["bitcoin", "10Y", "ES", "corn"],
                                    "fomc": ["KXFED", "speeches"], "fiscal": ["TGA", "Debt to the Penny", "auctions"]}),
                         {"bls": ["CPI", "CPI_NSA", "PAYROLLS", "UNRATE"], "fx": ["USD", "JPY", "GBP", "CHF"], "cot": ["BTC", "TY", "ES"],
                          "fomc": ["fomc", "speeches"], "fiscal": ["tga", "debt", "auctions"]})
        self.assertIn("fx", feeds.HISTORY_FEEDS)
        self.assertIn("cot", feeds.HISTORY_FEEDS)
        self.assertNotIn("bls", feeds.HISTORY_FEEDS)
        hosts = feeds.league_hosts()
        for name in ("bls", "fiscal", "fx", "cot", "fomc"):
            self.assertIn(feeds.RECORDERS[name].host, hosts, name)

    def test_requests_name_them_without_taking_what_others_answer(self):
        self.assertEqual({name: request_feed(name) for name in (
            "cpi_release_values", "bls_payrolls_actuals", "cpi_consensus_forecast", "treasury_auction_results", "tga_balance",
            "ecb_reference_rates", "eurusd_daily_fixing_history", "cftc_cot_positioning", "commitments_of_traders",
            "fomc_meeting_calendar", "fed_speeches_schedule", "rates_desk_macro_calendar", "ust_10y_yield_history",
            "fed_funds_effective_rate", "cpi_history")},
            {"cpi_release_values": "bls", "bls_payrolls_actuals": "bls", "cpi_consensus_forecast": None,
             "treasury_auction_results": "fiscal", "tga_balance": "fiscal", "ecb_reference_rates": "fx",
             "eurusd_daily_fixing_history": "fx", "cftc_cot_positioning": "cot", "commitments_of_traders": "cot",
             "fomc_meeting_calendar": "fomc", "fed_speeches_schedule": "fomc", "rates_desk_macro_calendar": None,
             "ust_10y_yield_history": None, "fed_funds_effective_rate": "rates", "cpi_history": None})

    def test_describe_names_each_host_and_its_stamp(self):
        with tempfile.TemporaryDirectory() as root:
            store = FeedRecorder(path=Path(root) / "feeds.sqlite", clock=Clock("2026-09-25T06:40:00Z"),
                                 keys={"fx": ["USD"], "cot": ["BTC"], "bls": ["CPI"]})
            try:
                described = store.describe()
            finally:
                store.close()
        self.assertEqual((described["fx"]["host"], described["cot"]["host"], described["bls"]["host"]),
                         ("www.ecb.europa.eu", "publicreporting.cftc.gov", "api.bls.gov"))
        self.assertIn("17:00 Frankfurt", described["fx"]["point_in_time"])
        self.assertIn("seven days after its as-of Tuesday", described["cot"]["point_in_time"])
        self.assertIn("receive time", described["bls"]["point_in_time"])


if __name__ == "__main__":
    unittest.main()
