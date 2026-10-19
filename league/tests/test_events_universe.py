import datetime as dt
import json
import tempfile
import unittest

from league.events import calendar as C
from league.events import store as S
from league.events import universe as U

UTC = dt.timezone.utc


def weekdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


class FakeGateway:
    """Alpaca's calendar, assets and SIP daily bars, as the gateway answers them."""

    def __init__(self, closes):
        self.closes = closes  # {symbol: (close, volume)}
        self.calls = []

    def get_json(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        if path.endswith("/v2/calendar"):
            start, end = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
            return [{"date": d.isoformat(), "open": "09:30", "close": "13:00" if d == dt.date(2026, 11, 27) else "16:00"}
                    for d in weekdays(start, end) if d != dt.date(2026, 11, 26)]
        if path.endswith("/v2/assets"):
            return [{"symbol": s, "status": "active", "tradable": True, "class": "us_equity",
                     "exchange": "OTC" if s == "OTCX" else "NASDAQ"} for s in self.closes]
        if path.endswith("/v2/stocks/bars"):
            end = S.parse_iso(params["end"])
            start = dt.date.fromisoformat(params["start"])
            out = {}
            for sym in params["symbols"].split(","):
                c, v = self.closes[sym]
                out[sym] = [{"t": f"{d.isoformat()}T04:00:00Z", "o": c, "h": c, "l": c, "c": c, "v": v}
                            for d in weekdays(start, (end - dt.timedelta(minutes=1)).date())]
            return {"bars": out, "next_page_token": None}
        raise AssertionError(path)


def sec_feed(sic, form, date):
    return (f"<feed><company-info><assigned-sic>{sic}</assigned-sic></company-info>"
            f"<entry><filing-type>{form}</filing-type><filing-date>{date}</filing-date></entry></feed>").encode()


class UniverseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.gw = FakeGateway({"BIG": (50.0, 1_000_000), "CHEAP": (2.5, 10_000_000), "THIN": (10.0, 50_000),
                               "OTCX": (10.0, 1_000_000), "SPY": (700.0, 1e8)})
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.now = dt.datetime(2026, 10, 19, 12, 0, tzinfo=UTC)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_calendar_moments(self):
        s = C.session(self.st, dt.date(2026, 10, 19))
        self.assertEqual(s.open_decide, dt.datetime(2026, 10, 19, 13, 15, tzinfo=UTC))
        self.assertEqual(s.close_decide, dt.datetime(2026, 10, 19, 19, 46, tzinfo=UTC))
        early = C.session(self.st, dt.date(2026, 11, 27))
        self.assertTrue(early.early)
        self.assertEqual(early.close_decide, dt.datetime(2026, 11, 27, 17, 46, tzinfo=UTC))  # 12:46 EST
        self.assertIsNone(C.session(self.st, dt.date(2026, 11, 26)))
        # a filing knowable Fri 17:40 EDT enters Monday's open; one knowable Mon 08:59 EDT enters Monday's open too
        self.assertEqual(C.first_open_entry(self.st, dt.datetime(2026, 10, 16, 21, 40, tzinfo=UTC)).day, dt.date(2026, 10, 19))
        self.assertEqual(C.first_open_entry(self.st, dt.datetime(2026, 10, 19, 12, 59, tzinfo=UTC)).day, dt.date(2026, 10, 19))
        self.assertEqual(C.first_open_entry(self.st, dt.datetime(2026, 10, 19, 13, 0, tzinfo=UTC)).day, dt.date(2026, 10, 20))
        # C1's day 0: the first session whose close decision is after the knowable time
        self.assertEqual(C.first_close_decision(self.st, dt.datetime(2026, 10, 19, 19, 45, tzinfo=UTC)).day, dt.date(2026, 10, 19))
        self.assertEqual(C.first_close_decision(self.st, dt.datetime(2026, 10, 19, 19, 46, tzinfo=UTC)).day, dt.date(2026, 10, 20))
        self.assertEqual(C.nth(self.st, dt.date(2026, 10, 19), 3).day, dt.date(2026, 10, 21))
        self.assertEqual(C.nth(self.st, dt.date(2026, 11, 25), 2).day, dt.date(2026, 11, 27))  # Thanksgiving skipped
        # DST: Nov 2 2026 is EST, the open decision is 14:15Z
        self.assertEqual(C.session(self.st, dt.date(2026, 11, 2)).open_decide, dt.datetime(2026, 11, 2, 14, 15, tzinfo=UTC))

    def test_sip_end_never_reaches_the_last_15_minutes(self):
        now = dt.datetime(2026, 10, 19, 20, 20, tzinfo=UTC)
        self.assertEqual(U.sip_end(dt.date(2026, 10, 16), now), "2026-10-17T00:00:00Z")
        self.assertEqual(U.sip_end(dt.date(2026, 10, 19), now), "2026-10-19T20:04:00Z")

    def test_eligibility_rules(self):
        day = dt.date(2026, 10, 19)
        prior = C.previous(self.st, day, 20)
        U.fetch_daily_bars(self.st, self.gw, ["BIG", "CHEAP", "THIN", "OTCX"], prior[0].day, prior[-1].day, now=self.now)
        assets = U.alpaca_assets(self.gw)
        tickers = {"0000000001": [("BIG", "Big Co")], "0000000002": [("CHEAP", "Cheap Co")],
                   "0000000003": [("THIN", "Thin Co")], "0000000004": [("OTCX", "Otc Co")]}
        row = U.eligible(self.st, "0000000001", day, tickers=tickers, assets=assets, operating_ok=True)
        self.assertEqual((row["symbol"], row["bench"]), ("BIG", "SPY"))
        self.assertAlmostEqual(row["adv20"], 50_000_000.0)
        self.assertIsNone(U.eligible(self.st, "0000000002", day, tickers=tickers, assets=assets, operating_ok=True))  # < $3
        self.assertIsNone(U.eligible(self.st, "0000000003", day, tickers=tickers, assets=assets, operating_ok=True))  # ADV
        self.assertIsNone(U.eligible(self.st, "0000000004", day, tickers=tickers, assets=assets, operating_ok=True))  # OTC
        self.assertIsNone(U.eligible(self.st, "0000000001", day, tickers=tickers, assets=assets, operating_ok=False))

    def test_backfilled_days_take_the_listing_exchange_from_the_previous_closing_print(self):
        day = dt.date(2026, 10, 19)
        prior = C.previous(self.st, day, 20)
        U.fetch_daily_bars(self.st, self.gw, ["BIG"], prior[0].day, prior[-1].day, now=self.now)
        assets = {"BIG": {"symbol": "BIG", "status": "inactive", "tradable": False, "class": "us_equity", "exchange": "OTC"}}
        tickers = {"0000000001": [("BIG", "Big Co")]}
        # delisted since and now OTC in Alpaca's record: a live day refuses it; a backfilled day reads the print
        self.assertIsNone(U.eligible(self.st, "0000000001", day, tickers=tickers, assets=assets, operating_ok=True))
        assets["BIG"] = dict(assets["BIG"], exchange="NASDAQ")
        row = U.eligible(self.st, "0000000001", day, tickers=tickers, assets=assets, operating_ok=True, live=False,
                         listing=lambda sym: "NYSE")
        self.assertEqual(row["exchange"], "NYSE")
        self.assertIsNone(U.eligible(self.st, "0000000001", dt.date(2026, 10, 20), tickers=tickers, assets=assets,
                                     operating_ok=True, live=False, listing=lambda sym: None))

    def test_operating_company_test(self):
        feeds = {("0000000009", "10-"): sec_feed("3571", "10-Q", "2026-08-01"),
                 ("0000000008", "10-"): sec_feed("6221", "10-K", "2026-03-01"),
                 ("0000000007", "10-"): b"<feed></feed>", ("0000000007", "20-F"): sec_feed("2834", "20-F", "2026-04-01"),
                 ("0000000006", "10-"): sec_feed("3571", "10-Q", "2025-01-02"),
                 ("0000000006", "20-F"): b"<feed></feed>", ("0000000006", "40-F"): b"<feed></feed>"}
        calls = []

        def get(url):
            cik = url.split("CIK=")[1].split("&")[0]
            prefix = url.split("type=")[1].split("&")[0]
            calls.append((cik, prefix))
            return feeds.get((cik, prefix), b"<feed></feed>")
        day = dt.date(2026, 10, 19)
        self.assertTrue(U.operating(self.st, get, "0000000009", day, now=self.now))
        self.assertFalse(U.operating(self.st, get, "0000000008", day, now=self.now))  # commodity trust SIC
        self.assertTrue(U.operating(self.st, get, "0000000007", day, now=self.now))   # foreign private issuer
        self.assertFalse(U.operating(self.st, get, "0000000006", day, now=self.now))  # older than 15 months
        n = len(calls)
        self.assertTrue(U.operating(self.st, get, "0000000009", day, now=self.now))   # cached
        self.assertEqual(len(calls), n)
        # a backfilled day is judged on the filings BEFORE it: the 10-Q of Aug 1 does not make Jul 15 operating,
        # but an older 10-K inside 15 months does
        feeds[("0000000005", "10-")] = (b"<feed><company-info><assigned-sic>3571</assigned-sic></company-info>"
                                        b"<entry><filing-type>10-Q</filing-type><filing-date>2026-08-01</filing-date></entry>"
                                        b"<entry><filing-type>10-K</filing-type><filing-date>2026-03-01</filing-date></entry></feed>")
        self.assertTrue(U.operating(self.st, get, "0000000005", dt.date(2026, 7, 15), now=self.now))
        feeds[("0000000004", "10-")] = sec_feed("3571", "10-Q", "2026-08-01")
        feeds[("0000000004", "20-F")] = b"<feed></feed>"
        feeds[("0000000004", "40-F")] = b"<feed></feed>"
        self.assertFalse(U.operating(self.st, get, "0000000004", dt.date(2026, 7, 15), now=self.now))


if __name__ == "__main__":
    unittest.main()
