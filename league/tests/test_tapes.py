import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from league.tapes import (
    DAY,
    TIMEFRAME_SECONDS,
    AlpacaData,
    KalshiData,
    TapeError,
    is_crypto,
    iso,
    listed_close,
    load_env,
    parse_strike,
    parse_time,
    two_sided,
)

D = Decimal
NOW = parse_time("2026-09-10T14:02:00Z")


def clock() -> float:
    return NOW


class FakeClient:
    """A scripted `VenueClient`: answers in order, remembers what it was asked."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers=None, body=None, what="venue"):
        self.calls.append((method, url))
        if not self.responses:
            raise AssertionError(f"unexpected request: {url}")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def urls(self):
        return [url for _, url in self.calls]


def bar(t, close, *, volume="0.5"):
    """One Alpaca bar as `decode` hands it over: Decimals, plus fields the tape does not use."""
    c = D(str(close))
    return {"t": t, "o": c - 1, "h": c + 2, "l": c - 3, "c": c, "v": D(volume), "n": 3, "vw": c}


def ok(bars, token=None):
    return 200, {"bars": bars, "next_page_token": token}


class HelpersTest(unittest.TestCase):
    def test_is_crypto(self):
        self.assertTrue(is_crypto("BTC/USD"))
        self.assertFalse(is_crypto("SPY"))

    def test_timeframes(self):
        self.assertEqual(TIMEFRAME_SECONDS, {"1Min": 60, "5Min": 300, "15Min": 900, "1Hour": 3600, "1Day": 86400})

    def test_times_round_trip(self):
        self.assertEqual(iso(parse_time("2026-09-10T13:35:00Z")), "2026-09-10T13:35:00Z")
        self.assertEqual(parse_time("2026-09-10T13:35:00+00:00"), parse_time("2026-09-10T13:35:00Z"))
        self.assertEqual(parse_time("2026-09-10T09:35:00-04:00"), parse_time("2026-09-10T13:35:00Z"))
        self.assertEqual(int(parse_time("2026-09-10T13:35:00.123456789Z")), int(parse_time("2026-09-10T13:35:00Z")))
        self.assertEqual(parse_time(1789000000), 1789000000.0)
        for bad in ("", "yesterday", None, True):
            with self.assertRaises(TapeError):
                parse_time(bad)

    def test_parse_strike(self):
        self.assertEqual(parse_strike("KXBTCD-26SEP2017-T80999.99"), 80999.99)
        self.assertEqual(parse_strike("KXBTCD-26SEP2017-B81250"), 81250.0)
        self.assertIsInstance(parse_strike("KXBTCD-26SEP2017-B81250"), float)
        self.assertEqual(parse_strike("KXLOWT-26SEP20-T-5"), -5.0)
        self.assertEqual(parse_strike("KXMLBGAME-26SEP20NYYBOS-NYY", {"floor_strike": D("3.5")}), 3.5)
        self.assertEqual(parse_strike("KXMLBGAME-26SEP20NYYBOS-NYY", {"floor_strike": None, "cap_strike": D("7")}), 7.0)
        self.assertIsNone(parse_strike("KXMLBGAME-26SEP20NYYBOS-NYY", {}))
        self.assertIsNone(parse_strike("KXMLBGAME-26SEP20NYYBOS-NYY"))

    def test_two_sided(self):
        self.assertTrue(two_sided(0.91, 0.93))
        self.assertTrue(two_sided(0.5, 0.5))
        self.assertFalse(two_sided(0.0, 0.05))   # no bid
        self.assertFalse(two_sided(0.99, 1.0))   # no ask
        self.assertFalse(two_sided(0.6, 0.5))    # crossed
        self.assertFalse(two_sided(None, 0.5))

    def test_load_env(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("# a comment\nGATEWAY_TOKEN=abc=def\nexport OTHER='quoted value'\n\nnot a pair\n", encoding="utf-8")
            self.assertEqual(load_env(path), {"GATEWAY_TOKEN": "abc=def", "OTHER": "quoted value"})
            self.assertEqual(load_env(Path(folder) / "missing"), {})


class AlpacaBarsTest(unittest.TestCase):
    def test_crypto_url_close_stamp_floats_and_unclosed_bar(self):
        client = FakeClient(ok({"BTC/USD": [
            bar("2026-09-10T13:50:00Z", "81000.5"),
            bar("2026-09-10T13:55:00Z", "81010.25", volume="0"),
            bar("2026-09-10T14:00:00Z", "81020"),   # closes 14:05, after now (14:02): still forming
        ]}))
        out = AlpacaData(client, clock=clock).bars(["BTC/USD"], "5Min", limit=3)
        # No start: limit * timeframe * 2 plus an hour back from now, and one bar earlier still,
        # because the bar that closes at the start is stamped with its open.
        self.assertEqual(client.calls, [(
            "GET",
            "https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols=BTC/USD&timeframe=5Min"
            "&start=2026-09-10T12:27:00Z&end=2026-09-10T14:02:00Z&limit=10000",
        )])
        self.assertEqual(out, {"BTC/USD": [
            {"t": "2026-09-10T13:55:00Z", "o": 80999.5, "h": 81002.5, "l": 80997.5, "c": 81000.5, "v": 0.5},
            {"t": "2026-09-10T14:00:00Z", "o": 81009.25, "h": 81012.25, "l": 81007.25, "c": 81010.25, "v": 0.0},
        ]})
        for row in out["BTC/USD"]:
            for key in ("o", "h", "l", "c", "v"):
                self.assertIs(type(row[key]), float)

    def test_limit_keeps_the_most_recent(self):
        rows = [bar(iso(parse_time("2026-09-10T13:00:00Z") + 300 * i), 100 + i) for i in range(10)]
        out = AlpacaData(FakeClient(ok({"BTC/USD": rows})), clock=clock).bars(["BTC/USD"], "5Min", limit=4)
        self.assertEqual([row["c"] for row in out["BTC/USD"]], [106.0, 107.0, 108.0, 109.0])
        self.assertEqual(out["BTC/USD"][-1]["t"], "2026-09-10T13:50:00Z")

    def test_explicit_window_bounds_the_close_time_and_is_not_trimmed(self):
        rows = [bar(iso(parse_time("2026-09-10T12:50:00Z") + 300 * i), 100 + i) for i in range(8)]  # opens 12:50 .. 13:25
        client = FakeClient(ok({"BTC/USD": rows}))
        out = AlpacaData(client, clock=clock).bars(
            ["btc/usd"], "5Min", start="2026-09-10T13:00:00Z", end="2026-09-10T13:20:00Z", limit=2
        )
        self.assertIn("&start=2026-09-10T12:55:00Z&end=2026-09-10T13:20:00Z&", client.urls[0])
        self.assertEqual(
            [row["t"] for row in out["BTC/USD"]],
            ["2026-09-10T13:00:00Z", "2026-09-10T13:05:00Z", "2026-09-10T13:10:00Z", "2026-09-10T13:15:00Z", "2026-09-10T13:20:00Z"],
        )

    def test_an_end_in_the_future_is_now(self):
        client = FakeClient(ok({"BTC/USD": [bar("2026-09-10T14:00:00Z", 105)]}))
        out = AlpacaData(client, clock=clock).bars(["BTC/USD"], "5Min", start="2026-09-10T13:00:00Z", end="2026-09-11T00:00:00Z")
        self.assertIn("&end=2026-09-10T14:02:00Z&", client.urls[0])
        self.assertEqual(out, {"BTC/USD": []})

    def test_pagination_follows_the_token(self):
        client = FakeClient(
            ok({"BTC/USD": [bar("2026-09-10T13:00:00Z", 101)]}, token="abc123=="),
            ok({"BTC/USD": [bar("2026-09-10T13:05:00Z", 102)], "ETH/USD": [bar("2026-09-10T13:05:00Z", 103)]}),
        )
        out = AlpacaData(client, clock=clock).bars(["BTC/USD", "ETH/USD"], "5Min", limit=5)
        self.assertEqual(len(client.calls), 2)
        self.assertNotIn("page_token", client.urls[0])
        self.assertTrue(client.urls[1].startswith(client.urls[0]))
        self.assertTrue(client.urls[1].endswith("&page_token=abc123%3D%3D"))
        self.assertIn("symbols=BTC/USD,ETH/USD&", client.urls[0])
        self.assertEqual([row["c"] for row in out["BTC/USD"]], [101.0, 102.0])
        self.assertEqual([row["c"] for row in out["ETH/USD"]], [103.0])

    def test_page_cap_raises(self):
        client = FakeClient(*[ok({"BTC/USD": [bar("2026-09-10T13:00:00Z", 101)]}, token="more") for _ in range(3)])
        with self.assertRaisesRegex(TapeError, "more than 3 pages"):
            AlpacaData(client, clock=clock, max_pages=3).bars(["BTC/USD"], "5Min")
        self.assertEqual(len(client.calls), 3)

    def test_mixed_symbols_are_two_requests(self):
        client = FakeClient(
            ok({"BTC/USD": [bar("2026-09-10T13:55:00Z", 81000)]}),
            ok({"SPY": [bar("2026-09-10T13:50:00Z", 650, volume="1200")], "QQQ": []}),
        )
        out = AlpacaData(client, clock=clock).bars(["SPY", "BTC/USD", "QQQ"], "5Min", limit=120)
        self.assertEqual(len(client.calls), 2)
        crypto, stock = client.urls
        self.assertTrue(crypto.startswith("https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols=BTC/USD&timeframe=5Min&"))
        self.assertNotIn("feed=", crypto)
        # Equities: six times the span plus four days, to reach across closed hours and a weekend.
        start = iso(NOW - (120 * 300 * 6 + 4 * DAY) - 300)
        self.assertEqual(
            stock,
            "https://data.alpaca.markets/v2/stocks/bars?symbols=SPY,QQQ&timeframe=5Min"
            f"&start={start}&end=2026-09-10T14:02:00Z&limit=10000&feed=iex&adjustment=all",
        )
        self.assertEqual(list(out), ["SPY", "BTC/USD", "QQQ"])
        self.assertEqual(out["SPY"], [{"t": "2026-09-10T13:55:00Z", "o": 649.0, "h": 652.0, "l": 647.0, "c": 650.0, "v": 1200.0}])
        self.assertEqual(out["QQQ"], [])
        self.assertEqual(out["BTC/USD"][0]["t"], "2026-09-10T14:00:00Z")

    def test_default_lookback(self):
        look = AlpacaData.default_lookback
        self.assertEqual(look("5Min", 120, crypto=True), 120 * 300 * 2 + 3600)
        self.assertEqual(look("5Min", 120, crypto=False), 120 * 300 * 6 + 4 * DAY)
        self.assertEqual(look("5Min", 5000, crypto=False), 30 * DAY)      # capped
        self.assertEqual(look("1Day", 120, crypto=False), 120 * DAY * 1.5 + 5 * DAY)
        self.assertEqual(look("1Day", 5000, crypto=True), 800 * DAY)

    def test_daily_bar_closes_a_day_after_its_stamp(self):
        client = FakeClient(ok({"SPY": [bar("2026-09-08T04:00:00Z", 650), bar("2026-09-10T04:00:00Z", 655)]}))
        out = AlpacaData(client, clock=clock, feed="sip").bars(["SPY"], "1Day", limit=5)
        self.assertIn("&feed=sip&adjustment=all", client.urls[0])
        self.assertEqual([row["t"] for row in out["SPY"]], ["2026-09-09T04:00:00Z"])  # Sept 10's is still open

    def test_unusable_rows_are_dropped(self):
        good = bar("2026-09-10T13:00:00Z", 10)
        no_close = dict(bar("2026-09-10T13:05:00Z", 10), c=None)
        zero = dict(bar("2026-09-10T13:10:00Z", 10), l=D(0))
        no_time = dict(bar("2026-09-10T13:15:00Z", 10), t="soon")
        client = FakeClient(ok({"BTC/USD": [good, no_close, zero, no_time, "junk"], "DOGE/USD": [good]}))
        out = AlpacaData(client, clock=clock).bars(["BTC/USD"], "5Min")
        self.assertEqual([row["t"] for row in out["BTC/USD"]], ["2026-09-10T13:05:00Z"])
        self.assertEqual(list(out), ["BTC/USD"])  # a symbol nobody asked for is ignored

    def test_error_status_raises_a_clear_error(self):
        for status, payload, expected in (
            (403, {"message": "forbidden."}, "alpaca crypto bars: HTTP 403 forbidden."),
            (429, {"message": "too many requests"}, "HTTP 429 too many requests"),
            (502, {"message": "<html>bad gateway</html>"}, "HTTP 502"),
            (404, None, "alpaca crypto bars: HTTP 404"),
        ):
            with self.assertRaises(TapeError) as caught:
                AlpacaData(FakeClient((status, payload)), clock=clock).bars(["BTC/USD"], "5Min")
            self.assertIn(expected, str(caught.exception))
        with self.assertRaisesRegex(TapeError, "alpaca stock bars: HTTP 401"):
            AlpacaData(FakeClient((401, {"error": "unauthorized"})), clock=clock).bars(["SPY"], "5Min")

    def test_transport_failure_and_bad_shape_raise_tape_errors(self):
        with self.assertRaisesRegex(TapeError, "alpaca crypto bars: OSError: no route"):
            AlpacaData(FakeClient(OSError("no route")), clock=clock).bars(["BTC/USD"], "5Min")
        with self.assertRaisesRegex(TapeError, "not an object"):
            AlpacaData(FakeClient((200, ["bars"])), clock=clock).bars(["BTC/USD"], "5Min")
        with self.assertRaisesRegex(TapeError, "bars is not an object"):
            AlpacaData(FakeClient((200, {"bars": []})), clock=clock).bars(["BTC/USD"], "5Min")

    def test_bad_arguments(self):
        data = AlpacaData(FakeClient(), clock=clock)
        with self.assertRaisesRegex(TapeError, "timeframe"):
            data.bars(["BTC/USD"], "7Min")
        with self.assertRaisesRegex(TapeError, "symbol"):
            data.bars(["BTC/USD&feed=sip"], "5Min")
        with self.assertRaisesRegex(TapeError, "limit"):
            data.bars(["BTC/USD"], "5Min", limit=0)
        self.assertEqual(data.bars([], "5Min"), {})
        self.assertEqual(data.client.calls, [])


class AlpacaQuotesTest(unittest.TestCase):
    def test_quotes_urls_floats_and_one_sided_omitted(self):
        client = FakeClient(
            (200, {"quotes": {
                "ETH/USD": {"bp": D("2622.777"), "ap": D("2623.44"), "bs": D("0.03"), "t": "2026-09-10T14:01:59.050284359Z"},
                "BTC/USD": {"bp": D("80941.37"), "ap": D("80960.4")},
                "SOL/USD": {"bp": D("0"), "ap": D("140.1")},          # no bid
            }}),
            (200, {"quotes": {
                "SPY": {"bp": D("650.10"), "ap": 650, "ax": "V"},       # crossed
                "QQQ": {"bp": D("722.12"), "ap": D("722.21"), "bs": 280, "t": "2026-09-10T14:02:00Z"},
            }}),
        )
        out = AlpacaData(client, clock=clock).quotes(["BTC/USD", "SPY", "ETH/USD", "QQQ", "SOL/USD", "IWM"])
        self.assertEqual(client.urls, [
            "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=BTC/USD,ETH/USD,SOL/USD",
            "https://data.alpaca.markets/v2/stocks/quotes/latest?symbols=SPY,QQQ,IWM&feed=iex",
        ])
        self.assertEqual(out, {
            "BTC/USD": {"bid": 80941.37, "ask": 80960.4},
            "ETH/USD": {"bid": 2622.777, "ask": 2623.44, "t": "2026-09-10T14:01:59.050284Z"},
            "QQQ": {"bid": 722.12, "ask": 722.21, "t": "2026-09-10T14:02:00.000000Z"},
        })  # the quote's own time, when the venue gives one: a strategy may refuse a stale touch
        self.assertIs(type(out["QQQ"]["bid"]), float)

    def test_quotes_error(self):
        with self.assertRaisesRegex(TapeError, "alpaca stock quotes: HTTP 500"):
            AlpacaData(FakeClient((500, {"message": ""})), clock=clock).quotes(["SPY"])


class AlpacaTapeTest(unittest.TestCase):
    def test_one_step_per_distinct_close_across_symbols(self):
        client = FakeClient(ok({
            "BTC/USD": [bar("2026-09-10T12:50:00Z", 50), bar("2026-09-10T13:00:00Z", 81000), bar("2026-09-10T13:05:00Z", 81010),
                        bar("2026-09-10T13:15:00Z", 90)],
            "ETH/USD": [bar("2026-09-10T13:05:00Z", 2600), bar("2026-09-10T13:10:00Z", 2601)],
        }))
        tape = AlpacaData(client, clock=clock).tape(
            ["BTC/USD", "ETH/USD"], "5Min", start="2026-09-10T13:00:00Z", end="2026-09-10T13:15:00Z"
        )
        self.assertEqual(client.urls, [
            "https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols=BTC/USD,ETH/USD&timeframe=5Min"
            "&start=2026-09-10T12:55:00Z&end=2026-09-10T13:15:00Z&limit=10000"
        ])
        self.assertEqual(tape["venue"], "alpaca")
        self.assertEqual(tape["horizon"], "hour")
        self.assertEqual(tape["step_seconds"], 300)
        self.assertEqual(tape["half_spread_bps"], 2.0)
        self.assertNotIn("results", tape)
        self.assertEqual(tape["steps"], [
            {"t": "2026-09-10T13:05:00Z", "bars": {"BTC/USD": {"o": 80999.0, "h": 81002.0, "l": 80997.0, "c": 81000.0, "v": 0.5}}},
            {"t": "2026-09-10T13:10:00Z", "bars": {
                "BTC/USD": {"o": 81009.0, "h": 81012.0, "l": 81007.0, "c": 81010.0, "v": 0.5},
                "ETH/USD": {"o": 2599.0, "h": 2602.0, "l": 2597.0, "c": 2600.0, "v": 0.5},
            }},
            {"t": "2026-09-10T13:15:00Z", "bars": {"ETH/USD": {"o": 2600.0, "h": 2603.0, "l": 2598.0, "c": 2601.0, "v": 0.5}}},
        ])
        times = [step["t"] for step in tape["steps"]]
        self.assertEqual(times, sorted(set(times)))

    def test_half_spread_default_and_override(self):
        def responses():
            return (ok({"BTC/USD": [bar("2026-09-10T13:00:00Z", 81000)]}), ok({"SPY": [bar("2026-09-10T13:30:00Z", 650)]}))

        window = {"start": "2026-09-10T13:00:00Z", "end": "2026-09-10T14:00:00Z"}
        mixed = AlpacaData(FakeClient(*responses()), clock=clock).tape(["BTC/USD", "SPY"], "5Min", horizon="day", **window)
        self.assertEqual(mixed["half_spread_bps"], 1.0)
        self.assertEqual(mixed["horizon"], "day")
        self.assertEqual([sorted(step["bars"]) for step in mixed["steps"]], [["BTC/USD"], ["SPY"]])
        given = AlpacaData(FakeClient(*responses()), clock=clock).tape(["BTC/USD", "SPY"], "5Min", half_spread_bps=5, **window)
        self.assertEqual(given["half_spread_bps"], 5.0)
        self.assertIs(type(given["half_spread_bps"]), float)

    def test_a_tape_never_holds_an_unclosed_bar(self):
        client = FakeClient(ok({"BTC/USD": [bar("2026-09-10T13:55:00Z", 101), bar("2026-09-10T14:00:00Z", 102)]}))
        tape = AlpacaData(client, clock=clock).tape(["BTC/USD"], "5Min", start="2026-09-10T13:00:00Z", end="2026-09-10T15:00:00Z")
        self.assertEqual([step["t"] for step in tape["steps"]], ["2026-09-10T14:00:00Z"])

    def test_bad_arguments(self):
        data = AlpacaData(FakeClient(), clock=clock)
        window = {"start": "2026-09-10T13:00:00Z", "end": "2026-09-10T14:00:00Z"}
        with self.assertRaisesRegex(TapeError, "horizon"):
            data.tape(["BTC/USD"], "5Min", horizon="week", **window)
        with self.assertRaisesRegex(TapeError, "end must come after"):
            data.tape(["BTC/USD"], "5Min", start=window["end"], end=window["start"])
        with self.assertRaisesRegex(TapeError, "at least one symbol"):
            data.tape([], "5Min", **window)
        with self.assertRaisesRegex(TapeError, "half_spread_bps"):
            data.tape(["BTC/USD"], "5Min", half_spread_bps=-1, **window)


# ---------------------------------------------------------------------- kalshi

class FakeMarketData:
    """`KalshiMarketData.markets`: parsed rows (Decimal dollars) a page at a time."""

    def __init__(self, pages):
        self.pages = pages  # {series: [[row, ...], ...]}
        self.calls = []

    def markets(self, **kwargs):
        self.calls.append(kwargs)
        pages = self.pages.get(kwargs["series_ticker"], [[]])
        index = int(kwargs.get("cursor") or 0)
        return {"markets": pages[index], "cursor": str(index + 1) if index + 1 < len(pages) else ""}


def live(ticker, bid, ask, close, **extra):
    row = {
        "ticker": ticker, "event_ticker": "-".join(ticker.split("-")[:2]), "title": "Bitcoin price on Sep 10, 2026?",
        "status": "active", "yes_bid": None if bid is None else D(bid), "yes_ask": D(ask), "close_time": close,
        "volume_24h": D("12000.00"), "open_interest": D("3400.50"), "floor_strike": None, "cap_strike": None,
    }
    row.update(extra)
    return row


class SharedListingTest(unittest.TestCase):
    """Measured Sept 19, 2026: 26 agents waking together drew HTTP 429 from Kalshi."""

    def rows(self):
        return {"KXBTCD": [[live("KXBTCD-26SEP1011-T81099.99", "0.40", "0.44", "2026-09-10T15:00:00Z")]]}

    def test_a_series_is_read_once_and_shared_until_it_is_a_minute_old(self):
        now = [NOW]
        source = FakeMarketData(self.rows())
        data = KalshiData(source, clock=lambda: now[0], sleep=lambda s: None)
        for hours in (12, 6, 30):  # an hourly agent, another, and a daily one
            self.assertEqual(len(data.markets(["KXBTCD"], max_hours_to_close=hours)), 1)
        self.assertEqual(len(source.calls), 1)
        now[0] += 61
        data.markets(["KXBTCD"], max_hours_to_close=12)
        self.assertEqual(len(source.calls), 2)

    def test_a_daily_caller_may_accept_an_older_listing(self):
        now = [NOW]
        source = FakeMarketData(self.rows())
        data = KalshiData(source, clock=lambda: now[0], sleep=lambda s: None)
        data.markets(["KXBTCD"], max_hours_to_close=12)
        now[0] += 200
        data.markets(["KXBTCD"], max_hours_to_close=12, max_age=300)
        self.assertEqual(len(source.calls), 1)
        data.markets(["KXBTCD"], max_hours_to_close=12)  # an hourly caller wants it fresh
        self.assertEqual(len(source.calls), 2)

    def test_a_longer_window_than_the_shared_read_covers_is_read_again(self):
        source = FakeMarketData(self.rows())
        data = KalshiData(source, clock=clock, sleep=lambda s: None)
        data.markets(["KXBTCD"], max_hours_to_close=12)
        data.markets(["KXBTCD"], max_hours_to_close=60)
        self.assertEqual(len(source.calls), 2)

    def test_a_rate_limit_is_waited_out_and_asked_again(self):
        waits = []

        class Busy(FakeMarketData):
            def markets(self, **kwargs):
                if len(self.calls) < 2:
                    self.calls.append(kwargs)
                    raise RuntimeError("kalshi markets: HTTP 429 from https://api.elections.kalshi.com/...")
                return super().markets(**kwargs)

        source = Busy(self.rows())
        data = KalshiData(source, clock=clock, sleep=waits.append, min_interval=0)
        self.assertEqual(len(data.markets(["KXBTCD"], max_hours_to_close=12)), 1)
        self.assertEqual([w for w in waits if w >= 1], [1.0, 2.0])

    def test_a_rate_limit_that_does_not_lift_is_an_error_and_other_errors_are_not_retried(self):
        class Down(FakeMarketData):
            def __init__(self, text):
                super().__init__({})
                self.text = text

            def markets(self, **kwargs):
                self.calls.append(kwargs)
                raise RuntimeError(self.text)

        limited = Down("HTTP 429")
        with self.assertRaises(TapeError):
            KalshiData(limited, clock=clock, sleep=lambda s: None).markets(["KXBTCD"], max_hours_to_close=12)
        self.assertEqual(len(limited.calls), 4)
        broken = Down("HTTP 500")
        with self.assertRaises(TapeError):
            KalshiData(broken, clock=clock, sleep=lambda s: None).markets(["KXBTCD"], max_hours_to_close=12)
        self.assertEqual(len(broken.calls), 1)

    def test_reads_are_paced(self):
        waits = []
        source = FakeMarketData({"KXBTCD": [[]], "KXETHD": [[]], "KXSOLD": [[]]})
        KalshiData(source, clock=clock, sleep=waits.append, min_interval=5.0).markets(["KXBTCD", "KXETHD", "KXSOLD"], max_hours_to_close=12)
        self.assertEqual(len(waits), 2)  # nothing before the first read, a wait before each of the others
        self.assertTrue(all(4.9 < w <= 5.0 for w in waits), waits)


class ListedStopTest(unittest.TestCase):
    """What a replay shows as a settled market's close must be what the live view showed while it
    was open, never the moment the result was really declared."""

    def test_a_settled_game_shows_its_scheduled_expiration(self):
        from league.tapes import _listed_stop, parse_time

        row = {"can_close_early": True, "close_time": "2026-09-18T03:29:53Z", "expected_expiration_time": "2026-09-18T03:15:00Z",
               "expiration_time": "2026-09-18T03:15:00Z", "latest_expiration_time": "2026-09-20T00:15:00Z"}
        self.assertEqual(iso(_listed_stop(row, parse_time(row["close_time"]))), "2026-09-18T03:15:00Z")

    def test_a_market_that_cannot_close_early_shows_its_close(self):
        from league.tapes import _listed_stop, parse_time

        row = {"can_close_early": False, "close_time": "2026-09-18T15:00:00Z", "expiration_time": "2026-09-18T10:00:00Z"}
        self.assertEqual(iso(_listed_stop(row, parse_time(row["close_time"]))), "2026-09-18T15:00:00Z")

    def test_a_weather_market_stops_at_its_close_and_is_paid_later(self):
        from league.tapes import _listed_stop, parse_time, resolve_time

        row = {"can_close_early": True, "close_time": "2026-09-19T05:00:00Z", "expected_expiration_time": "2026-09-19T19:00:00Z",
               "expiration_time": "2026-09-19T19:00:00Z"}
        close = parse_time(row["close_time"])
        self.assertEqual((iso(_listed_stop(row, close)), iso(resolve_time(row, close))), ("2026-09-19T05:00:00Z", "2026-09-19T19:00:00Z"))


class ScheduledExpirationTest(unittest.TestCase):
    """X2 (Sept 24, 2026): a Kalshi market is expected to pay at its SCHEDULED (expected) expiration
    when the venue gives one, and at its close otherwise -- never at the latest moment it may expire.

    The venue gives one for every market seen (review of #249): all 993,336 settled rows of Sept 5-17
    in the local history cache and all 368,425 open rows of the first run's Sept 15 cache carry
    `expected_expiration_time`. For the daily diesel print it IS the week-out deadline, equal to the
    latest expiration (KXDIESELD-26SEP13-T6.210 closed 05:59Z Sept 13, expected and latest 07:30Z Sept
    20, paid 07:45Z Sept 13). So the T0 refusal of KXDIESELD-26SEP22-T6.510 at 03:18:43Z on Sept 22,
    "expected to resolve in 172 hours", is this rule judging by the venue's own schedule: X2 does not
    admit it. (And KXGOOGSHARE-26SEP21 was refused at 199 hours on Sept 19: only an OPEN row's expected
    expiration, its close plus seven days, gives that; its deprecated `expiration_time` is its close.)
    The close stands in only for a market the venue gives no expected expiration, of which none was
    seen."""

    NOW = parse_time("2026-09-22T03:18:43Z")

    @staticmethod
    def venue_row(ticker, close, **extra):
        """What Kalshi's /markets answers, before the House's parser."""
        row = {"ticker": ticker, "event_ticker": "-".join(ticker.split("-")[:2]), "status": "active", "title": "a test market",
               "yes_bid_dollars": "0.9600", "yes_ask_dollars": "0.9800", "close_time": close, "volume_24h_fp": "12000.00",
               "open_interest_fp": "3400.00", "can_close_early": False}
        row.update(extra)
        return row

    def diesel(self):
        """The daily diesel print as the venue lists it (the shape of KXDIESELD-26SEP13-T6.210)."""
        return self.venue_row("KXDIESELD-26SEP22-T6.510", "2026-09-22T05:59:00Z", can_close_early=True,
                              expected_expiration_time="2026-09-29T07:30:00Z", expiration_time="2026-09-29T07:30:00Z",
                              latest_expiration_time="2026-09-29T07:30:00Z")

    def unscheduled(self):
        """A market the venue gave no expected expiration: none was seen; the rule's fallback."""
        return self.venue_row("KXDIESELD-26SEP22-T6.505", "2026-09-22T06:00:00Z", expected_expiration_time=None,
                              expiration_time="2026-09-29T07:30:00Z", latest_expiration_time="2026-09-29T07:30:00Z")

    def game(self):
        return self.venue_row("KXMLBGAME-26SEP22NYYBOS-NYY", "2026-09-24T02:00:00Z", can_close_early=True,
                              expected_expiration_time="2026-09-22T06:30:00Z", expiration_time="2026-09-29T02:00:00Z",
                              latest_expiration_time="2026-09-29T02:00:00Z")

    def data(self, *venue_rows):
        from ltcm.data.kalshi import KalshiMarketData

        parsed = {row["ticker"]: KalshiMarketData.parse_market(row) for row in venue_rows}

        class Venue(FakeMarketData):
            def market(self, ticker):
                return parsed[ticker]

        by_series: dict = {}
        for row in parsed.values():
            by_series.setdefault(row["ticker"].split("-")[0], []).append(row)
        return KalshiData(Venue({series: [rows] for series, rows in by_series.items()}), clock=lambda: self.NOW)

    def test_the_parser_keeps_the_scheduled_expiration_apart_from_the_latest(self):
        from ltcm.data.kalshi import KalshiMarketData

        self.assertEqual(KalshiMarketData.parse_market(self.diesel())["expected_expiration_time"], "2026-09-29T07:30:00Z")
        self.assertEqual(KalshiMarketData.parse_market(self.game())["expected_expiration_time"], "2026-09-22T06:30:00Z")
        self.assertIsNone(KalshiMarketData.parse_market(self.unscheduled())["expected_expiration_time"])

    def test_the_daily_diesel_print_is_judged_by_the_week_out_expiration_the_venue_schedules(self):
        """Review of #249: X2 changes nothing here. The venue schedules the diesel print's expiration a
        week out, so the rule still says what it said at T0: 172 hours."""
        data = self.data(self.diesel())
        due = parse_time("2026-09-29T07:30:00Z")
        self.assertEqual(data.resolution_of("KXDIESELD-26SEP22-T6.510"), (due, "scheduled"))
        self.assertEqual(round((data.resolves_at("KXDIESELD-26SEP22-T6.510") - self.NOW) / 3600), 172)

    def test_a_market_the_venue_gives_no_scheduled_expiration_is_judged_by_its_close(self):
        data = self.data(self.unscheduled())
        close = parse_time("2026-09-22T06:00:00Z")
        self.assertEqual(data.resolution_of("KXDIESELD-26SEP22-T6.505"), (close, "close"))
        self.assertEqual(data.resolves_at("KXDIESELD-26SEP22-T6.505"), close)

    def test_a_scheduled_expiration_is_what_a_market_is_judged_by(self):
        data = self.data(self.game())
        self.assertEqual(data.resolution_of("KXMLBGAME-26SEP22NYYBOS-NYY"), (parse_time("2026-09-22T06:30:00Z"), "scheduled"))

    def test_the_live_view_shows_the_hours_the_book_judges(self):
        data = self.data(self.diesel(), self.game())
        rows = {row["market"]: row for row in data.markets(["KXDIESELD", "KXMLBGAME"], max_hours_to_close=24)}
        diesel, game = rows["KXDIESELD-26SEP22-T6.510"], rows["KXMLBGAME-26SEP22NYYBOS-NYY"]
        self.assertEqual((diesel["hours_to_close"], diesel["hours_to_resolve"]), (2.6714, 172.1881))
        self.assertEqual((game["hours_to_close"], game["hours_to_resolve"]), (3.1881, 3.1881))

    def test_a_settled_market_on_a_replay_tape_is_judged_the_same_way(self):
        from ltcm.data.kalshi import KalshiMarketData
        from league.tapes import resolve_time

        for venue_row in (self.diesel(), self.unscheduled()):
            live = self.data(venue_row).resolves_at(venue_row["ticker"])
            row = KalshiMarketData.parse_market({**venue_row, "status": "finalized", "result": "yes"})
            self.assertEqual(resolve_time(row, parse_time(row["close_time"])), live)


class KalshiMarketsTest(unittest.TestCase):
    def test_a_game_is_shown_by_when_it_is_expected_to_end_not_by_its_listed_close(self):
        """Measured Sept 19, 2026: a game's close is two days after kickoff; it really closes when a
        winner is declared, near its scheduled expiration."""
        game = dict(can_close_early=True, expected_expiration_time="2026-09-10T20:15:00Z", expiration_time="2026-09-10T20:15:00Z")  # 6.3 hours from NOW
        data = FakeMarketData({"KXNFLGAME": [[
            live("KXNFLGAME-26SEP10AB-A", "0.60", "0.62", "2026-09-12T17:00:00Z", **game),
            live("KXNFLGAME-26SEP14CD-C", "0.60", "0.62", "2026-09-13T01:00:00Z", can_close_early=True, expected_expiration_time="2026-09-12T23:00:00Z"),  # next week's
        ]]})
        rows = KalshiData(data, clock=clock).markets(["KXNFLGAME"], max_hours_to_close=12)
        self.assertEqual([row["market"] for row in rows], ["KXNFLGAME-26SEP10AB-A"])
        self.assertEqual((rows[0]["close_time"], rows[0]["hours_to_close"], rows[0]["hours_to_resolve"]), ("2026-09-10T20:15:00Z", 6.2167, 6.2167))

    def test_a_market_paid_after_it_stops_trading_shows_both_times(self):
        data = FakeMarketData({"KXHIGHNY": [[live("KXHIGHNY-26SEP10-T78", "0.91", "0.93", "2026-09-10T20:00:00Z", can_close_early=True, expected_expiration_time="2026-09-11T10:00:00Z")]]})
        row = KalshiData(data, clock=clock).markets(["KXHIGHNY"], max_hours_to_close=24)[0]
        self.assertEqual((row["hours_to_close"], row["hours_to_resolve"]), (5.9667, 19.9667))

    def test_resolves_at_is_the_scheduled_expiration_and_not_knowing_is_none(self):
        class One:
            def __init__(self):
                self.calls = 0

            def market(self, ticker):
                self.calls += 1
                if ticker == "GONE":
                    raise RuntimeError("404")
                return {"ticker": ticker, "close_time": "2026-09-12T17:00:00Z", "expected_expiration_time": "2026-09-10T20:15:00Z" if ticker == "GAME" else None}

        source = One()
        data = KalshiData(source, clock=clock)
        self.assertEqual(iso(data.resolves_at("game")), "2026-09-10T20:15:00Z")
        self.assertEqual(iso(data.resolves_at("PLAIN")), "2026-09-12T17:00:00Z")
        self.assertIsNone(data.resolves_at("GONE"))
        data.resolves_at("GAME")
        self.assertEqual(source.calls, 3)  # a schedule is asked for once; a failure is asked again

    def test_the_exchange_shard_is_shown_only_where_the_venue_names_it(self):
        # Sept 23, 2026: the shard funder (league/shards.py) learns which shard a series trades on
        # from the listing; a strategy that never read the key sees the shape it always has.
        data = FakeMarketData({"KXMLBTOTAL": [[
            live("KXMLBTOTAL-26SEP231840STLPIT-8", "0.40", "0.44", "2026-09-10T15:00:00Z", exchange_index=3),
            live("KXMLBTOTAL-26SEP231840STLPIT-9", "0.40", "0.44", "2026-09-10T15:00:00Z"),
        ]]})
        rows = KalshiData(data, clock=clock).markets(["KXMLBTOTAL"], max_hours_to_close=24)
        self.assertEqual([row.get("exchange_index") for row in rows], [3, None])
        self.assertNotIn("exchange_index", rows[1])

    def test_snapshot_shape_filters_and_order(self):
        data = FakeMarketData({
            "KXBTCD": [
                [
                    live("KXBTCD-26SEP1017-T80999.99", "0.91", "0.93", "2026-09-10T21:00:00Z"),
                    live("KXBTCD-26SEP1011-T81099.99", "0.40", "0.44", "2026-09-10T15:00:00Z"),
                    live("KXBTCD-26SEP1011-T85099.99", "0.00", "0.02", "2026-09-10T15:00:00Z"),   # no bid
                    live("KXBTCD-26SEP1011-T70099.99", "0.98", "1.00", "2026-09-10T15:00:00Z"),   # no ask
                ],
                [
                    live("KXBTCD-26SEP1111-T81099.99", "0.40", "0.44", "2026-09-11T15:00:00Z"),   # 25 hours out
                    live("KXBTCD-26SEP1010-T81099.99", "0.40", "0.44", "2026-09-10T14:00:00Z"),   # already closed
                    live("KXBTCD-26SEP1012-T81099.99", "0.40", "0.44", "2026-09-10T16:00:00Z", status="closed"),
                    live("KXBTCD-26SEP1012-T81199.99", None, "0.44", "2026-09-10T16:00:00Z"),
                    live("KXBTCD-26SEP1012-T81299.99", "0.40", "0.44", "not a time"),
                    "junk",
                ],
            ],
            "KXETHD": [[live("KXETHD-26SEP1011-B2625", "0.10", "0.12", "2026-09-10T15:00:00Z", cap_strike=D("2650"))]],
        })
        rows = KalshiData(data, clock=clock).markets(["kxbtcd", "KXETHD"], max_hours_to_close=24)
        self.assertEqual([row["market"] for row in rows], [
            "KXBTCD-26SEP1011-T81099.99", "KXETHD-26SEP1011-B2625", "KXBTCD-26SEP1017-T80999.99",
        ])
        self.assertEqual(rows[0], {
            "market": "KXBTCD-26SEP1011-T81099.99", "series": "KXBTCD", "title": "Bitcoin price on Sep 10, 2026?",
            "yes_bid": 0.40, "yes_ask": 0.44, "close_time": "2026-09-10T15:00:00Z", "hours_to_close": 0.9667, "hours_to_resolve": 0.9667,
            "volume_24h": 12000.0, "open_interest": 3400.5, "strike": 81099.99,
        })
        self.assertEqual(rows[1]["strike"], 2625.0)
        self.assertEqual(rows[1]["series"], "KXETHD")
        for key in ("yes_bid", "yes_ask", "hours_to_close", "volume_24h", "open_interest", "strike"):
            self.assertIs(type(rows[0][key]), float, key)
        # What the venue was asked: open markets of one series, closing inside the window, paged.
        first, second, third = data.calls
        self.assertEqual(first, {
            "series_ticker": "KXBTCD", "status": "open", "limit": 1000, "cursor": None,
            "min_close_ts": int(NOW), "max_close_ts": int(NOW + 48 * 3600) + 72 * 3600, "mve_filter": "exclude",  # two days (one read serves hourly and daily agents), and further: a game lists a late close
        })
        self.assertEqual(second["cursor"], "1")
        self.assertEqual(third["series_ticker"], "KXETHD")

    def test_limit_keeps_the_soonest_and_hours_narrow_it(self):
        data = FakeMarketData({"KXBTCD": [[
            live("KXBTCD-26SEP1017-T80999.99", "0.91", "0.93", "2026-09-10T21:00:00Z"),
            live("KXBTCD-26SEP1011-T81099.99", "0.40", "0.44", "2026-09-10T15:00:00Z"),
            live("KXBTCD-26SEP1011-T80099.99", "0.80", "0.84", "2026-09-10T15:00:00Z"),
        ]]})
        kalshi = KalshiData(data, clock=clock)
        self.assertEqual([r["market"] for r in kalshi.markets(["KXBTCD"], limit=2)],
                         ["KXBTCD-26SEP1011-T80099.99", "KXBTCD-26SEP1011-T81099.99"])
        self.assertEqual(len(kalshi.markets(["KXBTCD"], max_hours_to_close=1)), 2)
        self.assertEqual(kalshi.markets(["KXBTCD"], max_hours_to_close=0.5), [])
        self.assertEqual(kalshi.markets([]), [])

    def test_errors(self):
        class Broken:
            def markets(self, **kwargs):
                raise RuntimeError("kalshi markets: HTTP 503")

        with self.assertRaisesRegex(TapeError, "kalshi markets KXBTCD: RuntimeError: kalshi markets: HTTP 503"):
            KalshiData(Broken(), clock=clock).markets(["KXBTCD"])
        with self.assertRaisesRegex(TapeError, "series"):
            KalshiData(FakeMarketData({}), clock=clock).markets(["KXBTCD?x=1"])
        with self.assertRaisesRegex(TapeError, "max_hours_to_close"):
            KalshiData(FakeMarketData({}), clock=clock).markets(["KXBTCD"], max_hours_to_close=0)


class FakeHistory:
    """`History.kalshi_settled` rows (parsed, Decimal) and `kalshi_candles_many` flat candles."""

    def __init__(self, settled, candles):
        self.settled = settled
        self.candles = candles
        self.settled_calls = []
        self.candle_calls = []

    def kalshi_settled(self, series=None, *, start_ts, end_ts, max_pages=20, min_volume=0):
        self.settled_calls.append((series, start_ts, end_ts))
        return [
            row for row in self.settled
            if row["ticker"].startswith(series + "-") and start_ts <= parse_time(row["close_time"]) <= end_ts
        ]

    def kalshi_candles_many(self, tickers, *, start_ts, end_ts, period_minutes=60):
        names = list(tickers)
        self.candle_calls.append((names, start_ts, end_ts, period_minutes))
        return {name: list(self.candles.get(name, [])) for name in names}


def settled(ticker, result, open_time, close_time, **extra):
    row = {
        "ticker": ticker, "event_ticker": "-".join(ticker.split("-")[:2]), "title": "Bitcoin price on Sep 10, 2026?",
        "status": "finalized", "result": result, "yes_bid": D("0"), "yes_ask": D("1"), "open_time": open_time,
        "close_time": close_time, "can_close_early": True, "floor_strike": None, "cap_strike": None,
        "latest_expiration_time": None, "volume": D("10"),
    }
    row.update(extra)
    return row


def candle(at, bid, ask, *, ask_low=None, bid_high=None, volume=0.0, interest=0.0):
    """One `History.parse_candle` row: dollars as floats, `ts` the minute's end."""
    return {
        "ts": int(parse_time(at)), "yes_bid_close": bid, "yes_ask_close": ask,
        "yes_ask_low": ask if ask_low is None else ask_low, "yes_bid_high": bid if bid_high is None else bid_high,
        "yes_bid_open": bid, "yes_bid_low": bid, "yes_ask_open": ask, "yes_ask_high": ask,
        "price_close": None, "price_high": None, "price_low": None, "volume": volume, "open_interest": interest,
    }


A = "KXBTCD-26SEP1009-T80999.99"
B = "KXBTCD-26SEP1009-T99999.99"
C = "KXBTCD-26SEP1009-T81099.99"
E = "KXBTCD-26SEP1009B-B81250"
START, END = "2026-09-10T12:00:00Z", "2026-09-10T13:30:00Z"


def scripted_history():
    return FakeHistory(
        [
            settled(A, "yes", "2026-09-10T12:00:00Z", "2026-09-10T13:00:00Z"),
            settled(B, "no", "2026-09-10T12:00:00Z", "2026-09-10T13:00:00Z"),                 # no candles
            settled(C, "", "2026-09-10T12:00:00Z", "2026-09-10T13:00:00Z"),                   # voided
            settled(E, "no", "2026-09-10T12:30:00Z", "2026-09-10T13:30:00Z", floor_strike=D("81000"), cap_strike=D("81499.99")),
            settled("KXBTCD-26SEP1011-T80999.99", "yes", "2026-09-10T13:00:00Z", "2026-09-10T14:00:00Z"),  # closes after END
        ],
        {
            A: [
                candle("2026-09-10T12:03:00Z", 0.40, 0.44, ask_low=0.43, bid_high=0.41, volume=10.0, interest=10.0),
                candle("2026-09-10T12:07:00Z", 0.45, 0.47, ask_low=0.46, bid_high=0.46, volume=5.0, interest=15.0),
                candle("2026-09-10T12:09:00Z", 0.50, 0.52, ask_low=0.47, bid_high=0.51, volume=2.0, interest=17.0),
                candle("2026-09-10T12:21:00Z", 0.0, 0.05),                                    # the bid is gone
                candle("2026-09-10T12:33:00Z", 0.90, 0.93, ask_low=0.92, bid_high=0.91, interest=17.0),
                candle("2026-09-10T12:58:00Z", 0.99, 1.0),                                    # the ask is gone
                candle("2026-09-10T13:00:00Z", 0.99, 1.0),
            ],
            E: [candle("2026-09-10T12:31:00Z", 0.20, 0.25, volume=3.0, interest=3.0)],
        },
    )


class KalshiTapeTest(unittest.TestCase):
    def setUp(self):
        self.history = scripted_history()
        self.tape = KalshiData(None, self.history, clock=clock).tape(["KXBTCD"], start=START, end=END)
        self.by_time = {step["t"]: {row["market"]: row for row in step["markets"]} for step in self.tape["steps"]}

    def test_header_results_and_skipped_markets(self):
        tape = self.tape
        self.assertEqual((tape["venue"], tape["horizon"], tape["step_seconds"]), ("kalshi", "hour", 300))
        self.assertNotIn("half_spread_bps", tape)
        self.assertEqual(tape["results"], {A: "yes", E: "no"})  # no candles, voided and out-of-window: none of them
        self.assertEqual(tape["meta"], {"listed": 3, "scanned": 3, "kept": 2})
        times = [step["t"] for step in tape["steps"]]
        self.assertEqual(times, sorted(set(times)))
        self.assertTrue(all(step["markets"] for step in tape["steps"]))

    def test_a_market_lives_from_its_first_candle_to_its_close_while_two_sided(self):
        present = [t for t in sorted(self.by_time) if A in self.by_time[t]]
        self.assertEqual(present, [
            "2026-09-10T12:05:00Z", "2026-09-10T12:10:00Z", "2026-09-10T12:15:00Z", "2026-09-10T12:20:00Z",
            # 12:25 and 12:30: one-sided. 13:00 carries only the closing execution range.
            "2026-09-10T12:35:00Z", "2026-09-10T12:40:00Z", "2026-09-10T12:45:00Z", "2026-09-10T12:50:00Z",
            "2026-09-10T12:55:00Z", "2026-09-10T13:00:00Z",
        ])
        present = [t for t in sorted(self.by_time) if E in self.by_time[t]]
        self.assertEqual(present[0], "2026-09-10T12:35:00Z")
        self.assertEqual(present[-1], "2026-09-10T13:30:00Z")
        self.assertEqual(len(present), 12)

    def test_row_carries_the_last_candle_and_the_extremes_of_its_step(self):
        self.assertEqual(self.by_time["2026-09-10T12:05:00Z"][A], {
            "market": A, "series": "KXBTCD", "title": "Bitcoin price on Sep 10, 2026?",
            "yes_bid": 0.40, "yes_ask": 0.44, "yes_ask_low": 0.43, "yes_bid_high": 0.41,
            "close_time": "2026-09-10T13:00:00Z", "hours_to_close": 0.9167, "hours_to_resolve": 0.9167,
            "volume_24h": 10.0, "open_interest": 10.0, "strike": 80999.99,
        })
        row = self.by_time["2026-09-10T12:10:00Z"][A]   # two candles inside (12:05, 12:10]
        self.assertEqual((row["yes_bid"], row["yes_ask"], row["yes_ask_low"], row["yes_bid_high"]), (0.50, 0.52, 0.46, 0.51))
        self.assertEqual((row["volume_24h"], row["open_interest"]), (17.0, 17.0))
        row = self.by_time["2026-09-10T12:15:00Z"][A]   # none: the touch is carried, and is its own extreme
        self.assertEqual((row["yes_bid"], row["yes_ask"], row["yes_ask_low"], row["yes_bid_high"]), (0.50, 0.52, 0.52, 0.50))
        row = self.by_time["2026-09-10T12:35:00Z"][A]
        self.assertEqual((row["yes_bid"], row["yes_ask"], row["yes_ask_low"], row["yes_bid_high"]), (0.90, 0.93, 0.92, 0.91))
        for value in row.values():
            self.assertNotIsInstance(value, (int, D))

    def test_rows_are_ordered_by_close_and_strike_falls_back_to_the_ticker(self):
        step = next(step for step in self.tape["steps"] if step["t"] == "2026-09-10T12:35:00Z")
        self.assertEqual([row["market"] for row in step["markets"]], [A, E])
        self.assertEqual(step["markets"][1]["strike"], 81250.0)

    def test_history_is_asked_for_minute_candles_an_event_at_a_time(self):
        self.assertEqual(self.history.settled_calls, [("KXBTCD", int(parse_time(START)), int(parse_time(END)))])
        calls = {tuple(sorted(names)): (lo, hi, period) for names, lo, hi, period in self.history.candle_calls}
        self.assertEqual(calls, {
            (A, B): (parse_time("2026-09-10T12:00:00Z"), parse_time("2026-09-10T13:00:00Z"), 1),
            (E,): (parse_time("2026-09-10T12:00:00Z"), parse_time("2026-09-10T13:30:00Z"), 1),  # 12:30 open, whole hours
        })

    def test_step_seconds(self):
        tape = KalshiData(None, scripted_history(), clock=clock).tape(["KXBTCD"], start=START, end=END, step_seconds=900, horizon="day")
        self.assertEqual((tape["step_seconds"], tape["horizon"]), (900, "day"))
        rows = {step["t"]: {row["market"]: row for row in step["markets"]} for step in tape["steps"]}
        self.assertEqual(sorted(t for t in rows if A in rows[t]), ["2026-09-10T12:15:00Z", "2026-09-10T12:45:00Z", "2026-09-10T13:00:00Z"])
        first = rows["2026-09-10T12:15:00Z"][A]   # all three early candles fall inside (12:00, 12:15]
        self.assertEqual((first["yes_ask"], first["yes_ask_low"], first["yes_bid_high"]), (0.52, 0.43, 0.51))

    def test_long_lived_market_reads_a_day_of_warmup_and_volume_is_one_day(self):
        ticker = "KXBTCD-26SEP1017-T80999.99"
        history = FakeHistory(
            [settled(ticker, "no", "2026-09-03T21:00:00Z", "2026-09-10T13:00:00Z")],
            {ticker: [
                candle("2026-09-09T12:02:00Z", 0.30, 0.32, volume=100.0),
                candle("2026-09-09T12:30:00Z", 0.30, 0.33, volume=40.0),
                candle("2026-09-10T12:01:00Z", 0.31, 0.33, volume=7.0),
            ]},
        )
        tape = KalshiData(None, history, clock=clock).tape(["KXBTCD"], start=START, end=END)
        self.assertEqual(history.candle_calls[0][1:], (parse_time("2026-09-09T12:00:00Z"), parse_time("2026-09-10T13:00:00Z"), 1))
        first, second = tape["steps"][0], tape["steps"][1]
        self.assertEqual(first["t"], "2026-09-10T12:00:00Z")          # the touch from yesterday is carried in
        self.assertEqual((first["markets"][0]["yes_ask"], first["markets"][0]["volume_24h"]), (0.33, 140.0))
        self.assertEqual(second["markets"][0]["volume_24h"], 47.0)     # 12:02 yesterday has aged out

    def test_max_markets_takes_whole_events_and_bounds_the_reads(self):
        rows, candles = [], {}
        for hour in (9, 10, 11):
            for strike in ("T80999.99", "T81099.99"):
                ticker = f"KXBTCD-26SEP10{hour:02d}-{strike}"
                rows.append(settled(ticker, "yes" if strike == "T80999.99" else "no", "2026-09-10T12:00:00Z", "2026-09-10T13:00:00Z"))
                candles[ticker] = [candle("2026-09-10T12:01:00Z", 0.5, 0.6)]

        def build(cap, seed=7):
            history = FakeHistory(rows, candles)
            return KalshiData(None, history, clock=clock, seed=seed).tape(["KXBTCD"], start=START, end=END, max_markets=cap), history

        tape, history = build(3)
        self.assertEqual(len(tape["results"]), 3)
        self.assertEqual(len(history.candle_calls), 2)                 # the third event is never read
        self.assertEqual(tape["meta"], {"listed": 6, "scanned": 4, "kept": 3})
        events = sorted({name.rsplit("-", 1)[0] for name in tape["results"]})
        self.assertEqual(len(events), 2)
        shown = {row["market"] for step in tape["steps"] for row in step["markets"]}
        self.assertEqual(shown, set(tape["results"]))
        self.assertEqual(build(3)[0], tape)                            # the draw is deterministic
        self.assertEqual(len(build(400)[0]["results"]), 6)
        self.assertEqual(build(0)[0]["steps"], [])
        orders = {tuple(build(2, seed=seed)[0]["results"]) for seed in range(12)}
        self.assertGreater(len(orders), 1)                             # and the seed is what orders it

    def test_listing_is_cut_on_utc_days(self):
        history = FakeHistory([], {})
        tape = KalshiData(None, history, clock=clock).tape(["KXBTCD", "KXETHD"], start="2026-09-08T22:00:00Z", end="2026-09-10T02:00:00Z")
        self.assertEqual((tape["steps"], tape["results"]), ([], {}))
        day = parse_time("2026-09-09T00:00:00Z")
        windows = [(int(parse_time("2026-09-08T22:00:00Z")), int(day) - 1), (int(day), int(day) + DAY - 1),
                   (int(day) + DAY, int(parse_time("2026-09-10T02:00:00Z")))]
        self.assertEqual(history.settled_calls, [(name, lo, hi) for name in ("KXBTCD", "KXETHD") for lo, hi in windows])

    def test_an_early_close_shows_the_close_the_listing_showed(self):
        ticker = "KXMLBGAME-26SEP10NYYBOS-NYY"
        row = settled(ticker, "yes", "2026-09-10T11:00:00Z", "2026-09-10T12:47:13Z", latest_expiration_time="2026-09-12T00:00:00Z")
        self.assertEqual(listed_close(row, parse_time(row["close_time"])), parse_time("2026-09-12T00:00:00Z"))
        self.assertEqual(listed_close(dict(row, can_close_early=False), 5.0), 5.0)
        history = FakeHistory([row], {ticker: [candle("2026-09-10T12:31:00Z", 0.60, 0.62)]})
        tape = KalshiData(None, history, clock=clock).tape(["KXMLBGAME"], start=START, end=END)
        self.assertEqual([step["t"] for step in tape["steps"]], ["2026-09-10T12:35:00Z", "2026-09-10T12:40:00Z", "2026-09-10T12:45:00Z", "2026-09-10T12:47:13Z", END])
        self.assertTrue(tape["steps"][-1]["execution_only"])
        self.assertEqual(tape["steps"][-1]["markets"], [])
        shown = tape["steps"][-3]["markets"][0]
        self.assertEqual(shown["close_time"], "2026-09-12T00:00:00Z")   # never the moment the game ended
        self.assertEqual(shown["hours_to_close"], 35.25)
        self.assertIsNone(shown["strike"])
        terminal = tape["steps"][-2]["markets"][0]
        self.assertEqual(terminal["close_time"], "2026-09-10T12:47:13Z")
        self.assertIsNone(terminal["yes_bid"])
        self.assertIsNone(terminal["yes_ask"])

    def test_errors(self):
        with self.assertRaisesRegex(TapeError, "needs a History"):
            KalshiData(None, clock=clock).tape(["KXBTCD"], start=START, end=END)

        class BrokenListing(FakeHistory):
            def kalshi_settled(self, series=None, **kwargs):
                raise RuntimeError("HTTP 429")

        class BrokenCandles(FakeHistory):
            def kalshi_candles_many(self, tickers, **kwargs):
                raise RuntimeError("HTTP 500")

        with self.assertRaisesRegex(TapeError, "kalshi settled KXBTCD .*RuntimeError: HTTP 429"):
            KalshiData(None, BrokenListing([], {}), clock=clock).tape(["KXBTCD"], start=START, end=END)
        broken = BrokenCandles(scripted_history().settled, {})
        with self.assertRaisesRegex(TapeError, "kalshi candles KXBTCD-26SEP1009.*RuntimeError: HTTP 500"):
            KalshiData(None, broken, clock=clock).tape(["KXBTCD"], start=START, end=END)
        kalshi = KalshiData(None, scripted_history(), clock=clock)
        with self.assertRaisesRegex(TapeError, "step_seconds"):
            kalshi.tape(["KXBTCD"], start=START, end=END, step_seconds=30)
        with self.assertRaisesRegex(TapeError, "horizon"):
            kalshi.tape(["KXBTCD"], start=START, end=END, horizon="minute")
        with self.assertRaisesRegex(TapeError, "end must come after"):
            kalshi.tape(["KXBTCD"], start=END, end=START)
        with self.assertRaisesRegex(TapeError, "at least one series"):
            kalshi.tape([], start=START, end=END)


if __name__ == "__main__":
    unittest.main()
