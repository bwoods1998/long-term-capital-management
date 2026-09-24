"""Crypto derivatives: DVOL, funding across OKX/Hyperliquid/Kraken, the Deribit basis, a snapshot."""

from __future__ import annotations

import unittest

from ltcm.data import DataError
from ltcm.data.derivs import (
    DERIBIT_HOST,
    HYPERLIQUID_HOST,
    KRAKEN_HOST,
    OKX_HOST,
    USER_AGENT,
    Derivatives,
    expiry_of,
    zscore,
)
from ltcm.tests.fakes import Clock, FakeTransport, TransportError

DVOL = DERIBIT_HOST + "/api/v2/public/get_volatility_index_data?*"
INDEX = DERIBIT_HOST + "/api/v2/public/get_index_price?*"
FUTURES = DERIBIT_HOST + "/api/v2/public/get_book_summary_by_currency?*"
OKX_FUNDING = OKX_HOST + "/api/v5/public/funding-rate?*"
OKX_HISTORY = OKX_HOST + "/api/v5/public/funding-rate-history?*"
OKX_OI = OKX_HOST + "/api/v5/public/open-interest?*"
OKX_TICKER = OKX_HOST + "/api/v5/market/ticker?*"
HYPERLIQUID = ("POST", HYPERLIQUID_HOST + "/info")
KRAKEN = KRAKEN_HOST + "/derivatives/api/v3/tickers"

DVOL_JSON = {"jsonrpc": "2.0", "result": {"data": [
    [1789704000000, 34.26, 34.38, 34.19, 34.37],
    [1789700400000, 33.81, 34.32, 33.77, 34.26],
    [1789707600000, 34.37, 34.38, 34.16, "bad"],
], "continuation": None}}
INDEX_JSON = {"jsonrpc": "2.0", "result": {"estimated_delivery_price": 77591.46, "index_price": 77591.46}}
FUTURES_JSON = {"jsonrpc": "2.0", "result": [
    {"instrument_name": "BTC-9OCT26", "mark_price": 77802.56, "mid_price": 77801.25, "open_interest": 890780, "estimated_delivery_price": 77591.46, "creation_timestamp": 1789712730011},
    {"instrument_name": "BTC-PERPETUAL", "mark_price": 77607.36, "mid_price": 77606.75, "open_interest": 762751520, "estimated_delivery_price": 77591.46},
    {"instrument_name": "BTC-18SEP26", "mark_price": 77593.52, "mid_price": 77586.25, "open_interest": 19012760, "estimated_delivery_price": None},
    {"instrument_name": "BTC-BROKEN", "mark_price": None},
]}
OKX_FUNDING_JSON = {"code": "0", "data": [{"fundingRate": "0.0000406772451918", "fundingTime": "1789718400000", "instId": "BTC-USDT-SWAP",
                                            "nextFundingRate": "", "nextFundingTime": "1789747200000", "premium": "-0.0004249171411574"}], "msg": ""}
OKX_HISTORY_JSON = {"code": "0", "data": [{"fundingRate": str(0.00005 + i * 0.000002), "fundingTime": str(1789689600000 - i * 28800000)} for i in range(30)], "msg": ""}
OKX_OI_JSON = {"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "oi": "2876571.32", "oiCcy": "28765.71", "oiUsd": "2232794658.58"}], "msg": ""}
OKX_TICKER_JSON = {"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "last": "77619.9", "bidPx": "77619.8", "askPx": "77619.9"}], "msg": ""}
HYPERLIQUID_JSON = [
    {"universe": [{"szDecimals": 5, "name": "BTC", "maxLeverage": 40}, {"szDecimals": 4, "name": "ETH", "maxLeverage": 25}, {"name": "SOL"}], "marginTables": []},
    [
        {"funding": "0.0000113663", "openInterest": "35483.64326", "prevDayPx": "76413.0", "premium": "-0.0004197969", "oraclePx": "77656.6", "markPx": "77623.0", "midPx": "77623.5"},
        {"funding": "0.0000125", "openInterest": "1005433.3946", "premium": "-0.0000643382", "oraclePx": "2486.86", "markPx": "2486.6"},
        {"funding": None, "openInterest": "bad"},
    ],
]
KRAKEN_JSON = {"result": "success", "serverTime": "2026-09-18T06:25:37Z", "tickers": [
    {"symbol": "PF_XBTUSD", "tag": "perpetual", "pair": "XBT:USD", "markPrice": 77595.10, "openInterest": 2166.6523, "fundingRate": 1.0352445904, "fundingRatePrediction": 1.8903308169, "indexPrice": 77585.88},
    {"symbol": "PF_SOLUSD", "markPrice": 105.7, "openInterest": 500.0, "fundingRate": -0.0021, "fundingRatePrediction": 0.0},
    {"symbol": "FI_XBTUSD_260925", "markPrice": 77800.0, "fundingRate": None},
]}


class DerivativesCase(unittest.TestCase):
    def transport(self, overrides=None):
        routes = {
            DVOL: DVOL_JSON, INDEX: INDEX_JSON, FUTURES: FUTURES_JSON,
            OKX_FUNDING: OKX_FUNDING_JSON, OKX_HISTORY: OKX_HISTORY_JSON, OKX_OI: OKX_OI_JSON, OKX_TICKER: OKX_TICKER_JSON,
            HYPERLIQUID: HYPERLIQUID_JSON, KRAKEN: KRAKEN_JSON,
        }
        routes.update(overrides or {})
        return FakeTransport(routes)

    def derivs(self, transport=None):
        return Derivatives(transport or self.transport(), clock=Clock("2026-09-18T06:30:00Z"))


class DvolTests(DerivativesCase):
    def test_dvol_candles_are_hourly_sorted_and_windowed_by_the_clock(self):
        transport = self.transport()
        rows = self.derivs(transport).dvol("BTC", hours=48)
        self.assertEqual(rows, [
            {"t": "2026-09-18T03:00:00Z", "open": 33.81, "high": 34.32, "low": 33.77, "close": 34.26},
            {"t": "2026-09-18T04:00:00Z", "open": 34.26, "high": 34.38, "low": 34.19, "close": 34.37},
        ])
        query = transport.last["query"]
        self.assertEqual(query["currency"], "BTC")
        self.assertEqual(query["resolution"], "3600")
        self.assertEqual(int(query["end_timestamp"]) - int(query["start_timestamp"]), 48 * 3600 * 1000)
        self.assertEqual(int(query["end_timestamp"]), int(Clock("2026-09-18T06:30:00Z")() * 1000))
        self.assertEqual(transport.last["headers"]["User-Agent"], USER_AGENT)

    def test_dvol_now_is_the_latest_close_or_none(self):
        self.assertEqual(self.derivs().dvol_now("BTC"), 34.37)
        self.assertIsNone(self.derivs(self.transport({DVOL: {"result": {"data": []}}})).dvol_now("SOL"))
        self.assertIsNone(self.derivs(self.transport({DVOL: (502, {}, b"bad gateway")})).dvol_now("BTC"))
        self.assertIsNone(self.derivs(self.transport({DVOL: TransportError("dns")})).dvol_now("BTC"))
        with self.assertRaises(DataError):
            self.derivs(self.transport({DVOL: {"jsonrpc": "2.0", "error": {"code": 1}}})).dvol("BTC")


class HistoryTests(DerivativesCase):
    """The paginated history league/feeds.py backfills from (Sept 23, 2026): unlike the snapshot
    helpers, these raise when the venue fails, so a failed poll is never read as an empty one."""

    def test_dvol_candles_are_a_range_oldest_first_with_the_continuation(self):
        answer = {"jsonrpc": "2.0", "result": {"data": [[1789704000000, 34.26, 34.38, 34.19, 34.37], [1789700400000, 33.81, 34.32, 33.77, 34.26],
                                                        [1789707600000, 34.37, 34.38, 34.16, "bad"], [0, 1, 1, 1, 1]],
                                               "continuation": 1789700399999}}
        transport = self.transport({DVOL: answer})
        rows, more = self.derivs(transport).dvol_candles("btc", 1789600000000, 1789704000000)
        self.assertEqual(rows, [{"t_ms": 1789700400000, "open": 33.81, "high": 34.32, "low": 33.77, "close": 34.26},
                                {"t_ms": 1789704000000, "open": 34.26, "high": 34.38, "low": 34.19, "close": 34.37}])
        self.assertEqual(more, 1789700399999)
        self.assertEqual(transport.last["query"], {"currency": "BTC", "resolution": "3600", "start_timestamp": "1789600000000",
                                                   "end_timestamp": "1789704000000"})
        self.assertEqual(self.derivs().dvol_candles("BTC", 1, 2)[1], None)  # the whole range came back
        with self.assertRaises(TransportError):
            self.derivs(self.transport({DVOL: TransportError("dns")})).dvol_candles("BTC", 1, 2)
        with self.assertRaises(DataError):
            self.derivs(self.transport({DVOL: {"jsonrpc": "2.0", "error": {"code": 1}}})).dvol_candles("BTC", 1, 2)

    def test_okx_settled_funding_pages_back_and_prefers_the_realized_rate(self):
        answer = {"code": "0", "msg": "", "data": [
            {"instId": "BTC-USDT-SWAP", "fundingRate": "0.0002", "realizedRate": "0.00019", "fundingTime": "1789689600000"},
            {"instId": "BTC-USDT-SWAP", "fundingRate": "0.0001", "fundingTime": "1789660800000"},
            {"instId": "BTC-USDT-SWAP", "fundingRate": "0.0001", "fundingTime": "x"}]}
        transport = self.transport({OKX_HISTORY: answer})
        rows = self.derivs(transport).okx_funding_settled("btc", after_ms=1789700000000, limit=500)
        self.assertEqual(rows, [{"time_ms": 1789689600000, "rate": 0.00019, "funding_rate": 0.0002, "realized_rate": 0.00019},
                                {"time_ms": 1789660800000, "rate": 0.0001, "funding_rate": 0.0001, "realized_rate": None}])
        self.assertEqual(transport.last["query"], {"instId": "BTC-USDT-SWAP", "limit": "100", "after": "1789700000000"})
        self.derivs(transport).okx_funding_settled("ETH")  # the newest page: no cursor
        self.assertEqual(transport.last["query"], {"instId": "ETH-USDT-SWAP", "limit": "100"})
        with self.assertRaises(DataError) as caught:
            self.derivs(self.transport({OKX_HISTORY: {"code": "51001", "data": [], "msg": "Instrument ID does not exist"}})).okx_funding_settled("ZZZ")
        self.assertIn("okx code 51001", str(caught.exception))
        with self.assertRaises(TransportError):
            self.derivs(self.transport({OKX_HISTORY: TransportError("refused")})).okx_funding_settled("BTC")


class FundingTests(DerivativesCase):
    def test_funding_reads_all_three_venues(self):
        transport = self.transport()
        answer = self.derivs(transport).funding("btc")
        self.assertEqual(answer["symbol"], "BTC")
        okx = answer["okx"]
        self.assertEqual(okx["instrument"], "BTC-USDT-SWAP")
        self.assertAlmostEqual(okx["rate"], 0.0000406772451918)
        self.assertIsNone(okx["next_rate"], "OKX sends an empty string before the next rate is known")
        self.assertEqual(okx["time"], "2026-09-18T08:00:00Z")
        self.assertEqual(okx["next_time"], "2026-09-18T16:00:00Z")
        self.assertEqual(okx["interval_hours"], 8)
        self.assertEqual(okx["open_interest_usd"], 2232794658.58)
        self.assertEqual(okx["last"], 77619.9)
        hl = answer["hyperliquid"]
        self.assertEqual((hl["rate"], hl["open_interest"], hl["mark"], hl["oracle"], hl["premium"], hl["interval_hours"]),
                         (0.0000113663, 35483.64326, 77623.0, 77656.6, -0.0004197969, 1))
        kraken = answer["kraken"]
        self.assertEqual(kraken["symbol"], "PF_XBTUSD", "Kraken spells Bitcoin XBT")
        self.assertEqual(kraken["rate"], round(1.0352445904 / 77595.10, 10))
        self.assertEqual(kraken["next_rate"], round(1.8903308169 / 77595.10, 10))
        self.assertEqual(kraken["open_interest"], 2166.6523)
        self.assertEqual(kraken["interval_hours"], 1)
        self.assertEqual(answer["as_of"], "2026-09-18T06:30:00Z")
        post = [c for c in transport.calls if c["method"] == "POST"]
        self.assertEqual(len(post), 1)
        self.assertEqual(post[0]["url"], HYPERLIQUID_HOST + "/info")
        self.assertEqual(post[0]["body"], {"type": "metaAndAssetCtxs"})
        self.assertEqual(post[0]["headers"]["Content-Type"], "application/json")
        self.assertEqual(post[0]["headers"]["User-Agent"], USER_AGENT)

    def test_a_venue_that_is_down_is_none_not_an_error(self):
        transport = self.transport({OKX_FUNDING: (500, {}, b"x"), HYPERLIQUID: TransportError("refused"), KRAKEN: {"tickers": "junk"}})
        answer = self.derivs(transport).funding("BTC")
        self.assertEqual((answer["okx"], answer["hyperliquid"], answer["kraken"]), (None, None, None))
        # An OKX open-interest failure still leaves the funding rate in place.
        partial = self.derivs(self.transport({OKX_OI: {"code": "50011", "data": [], "msg": "rate limit"}})).funding("BTC")
        self.assertAlmostEqual(partial["okx"]["rate"], 0.0000406772451918)
        self.assertIsNone(partial["okx"]["open_interest_usd"])
        self.assertIsNone(self.derivs().funding("DOGE")["hyperliquid"])


class BasisTests(DerivativesCase):
    def test_the_futures_curve_is_marked_against_the_index(self):
        rows = self.derivs().basis("BTC")
        self.assertEqual([r["instrument"] for r in rows], ["BTC-PERPETUAL", "BTC-18SEP26", "BTC-9OCT26"], "perpetual first, then by expiry")
        self.assertEqual(rows[2]["expiry"], "2026-10-09")
        self.assertEqual(rows[2]["basis_pct"], 0.2721)
        self.assertEqual(rows[2]["open_interest"], 890780.0)
        self.assertIsNone(rows[0]["expiry"])
        self.assertEqual(rows[1]["index"], 77591.46, "a missing delivery price falls back to the index")
        self.assertEqual(expiry_of("ETH-27MAR27"), "2027-03-27")
        self.assertIsNone(expiry_of("BTC-PERPETUAL"))
        self.assertIsNone(expiry_of("BTC-31FEB26"))
        with self.assertRaises(DataError):
            self.derivs(self.transport({FUTURES: {"result": "nope"}})).basis("BTC")


class SnapshotTests(DerivativesCase):
    def test_a_snapshot_has_funding_dvol_and_a_funding_z_per_symbol(self):
        transport = self.transport()
        rows = self.derivs(transport).snapshot(("BTC", "SOL"))
        self.assertEqual([r["symbol"] for r in rows], ["BTC", "SOL"])
        btc, sol = rows
        self.assertEqual(btc["dvol"], 34.37)
        self.assertIsNone(sol["dvol"], "DVOL exists for BTC and ETH only; nothing is fetched for SOL")
        self.assertEqual(btc["funding_history_n"], 30)
        # History runs 0.00005 .. 0.000108 (mean 0.000079, sd ~1.77e-5); the current 0.0000407 is about -2.2 sd.
        self.assertAlmostEqual(btc["funding_z"], -2.16, places=1)
        self.assertEqual(btc["kraken"]["symbol"], "PF_XBTUSD")
        self.assertEqual(sol["kraken"]["symbol"], "PF_SOLUSD")
        self.assertIsNone(sol["hyperliquid"]["rate"])
        self.assertEqual(sum(1 for c in transport.calls if c["method"] == "POST"), 1, "Hyperliquid is fetched once for all symbols")
        self.assertEqual(sum(1 for c in transport.calls if c["url"] == KRAKEN), 1)

    def test_zscore_needs_history(self):
        self.assertIsNone(zscore(0.1, [0.1, 0.2]))
        self.assertEqual(zscore(0.1, [0.1, 0.1, 0.1]), 0.0)
        self.assertIsNone(zscore(None, [1, 2, 3]))
        self.assertEqual(zscore(4.0, [1.0, 2.0, 3.0]), 2.0)


if __name__ == "__main__":
    unittest.main()


# ------------------------------------------------------- open interest history, Sept 24, 2026
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

OKX_OI_HISTORY = OKX_HOST + "/api/v5/rubik/stat/contracts/open-interest-history"


def recorded_oi():
    """okx open-interest-history for BTC-USDT-SWAP, 1H, recorded Sept 24, 2026 at 03:16Z."""
    return _json.loads((_Path(__file__).parent / "fixtures" / "feeds" / "okx_open_interest_history_btc.json").read_text(encoding="utf-8"))


class OpenInterestHistory(unittest.TestCase):
    def test_the_recorded_page_newest_first_and_paged_by_end(self):
        transport = FakeTransport({OKX_OI_HISTORY: recorded_oi()})
        rows = Derivatives(transport).okx_open_interest_history("btc", end_ms=1790222400000)
        self.assertEqual(rows[0], {"ts_ms": 1790218800000, "oi_contracts": 2948889.56000001215, "oi_coin": 29486.1667000001212,
                                   "oi_usd": 2484132880.44159021078488})
        self.assertEqual([r["ts_ms"] for r in rows], sorted((r["ts_ms"] for r in rows), reverse=True))
        self.assertEqual(transport.last["query"], {"instId": "BTC-USDT-SWAP", "period": "1H", "limit": "100", "end": "1790222400000"})

    def test_an_instrument_okx_does_not_list_says_so(self):
        transport = FakeTransport({OKX_OI_HISTORY: {"code": "51001", "data": [], "msg": "Instrument ID doesn't exist."}})
        with self.assertRaises(DataError) as caught:
            Derivatives(transport).okx_open_interest_history("ZZZ")
        self.assertIn("okx code 51001", str(caught.exception))
