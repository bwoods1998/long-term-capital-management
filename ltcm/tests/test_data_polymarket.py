"""Polymarket: the Gamma market page filtered locally, one market, the CLOB book and history."""

from __future__ import annotations

import unittest

from ltcm.data import DataError
from ltcm.data.polymarket import (
    CLOB_HOST,
    GAMMA_HOST,
    USER_AGENT,
    Polymarket,
    market_row,
    tokens,
)
from ltcm.tests.fakes import Clock, FakeTransport

PAGE = GAMMA_HOST + "/markets?limit=100&order=volume24hr&ascending=false&active=true&closed=false"
TOKEN_YES = "20915769520649892253891152116814645067070024223185517956799957803974344024878"
TOKEN_NO = "115351075585746600277716377744935410125916932950844626289798775482755919708780"
CONDITION = "0x502a94e5c525766d5ee7f16c6568131ba1b2cbadb69c703af05a6ef00336ed64"


def gamma_market(market_id, question, slug, prices=("0.765", "0.235"), volume=622762.12, **extra):
    row = {
        "id": market_id,
        "question": question,
        "slug": slug,
        "conditionId": CONDITION if market_id == "1130012" else "0x" + market_id.rjust(64, "0"),
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["%s", "%s"]' % prices,
        "clobTokenIds": '["%s", "%s"]' % (TOKEN_YES, TOKEN_NO),
        "volume24hr": volume,
        "liquidity": "705727.9141",
        "endDate": "2026-09-30T00:00:00Z",
        "active": True,
        "closed": False,
    }
    row.update(extra)
    return row


RUSSIA = gamma_market("1130012", "Will United Russia (ER) gain the most seats in the next Russian parliamentary election?",
                      "will-united-russia-er-gain-the-most-seats-in-the-next-russian-parliamentary-election")
FED_HOLD = gamma_market("1200001", "Will there be no change in Fed interest rates after the October 2026 meeting?",
                        "fed-no-change-october-2026", prices=("0.48", "0.52"), volume=250000.0)
FED_CUT = gamma_market("1200002", "Will the Fed decrease interest rates by 25 bps after the October 2026 meeting?",
                       "fed-decreases-interest-rates-by-25-bps-after-october-2026-meeting", prices=("0.505", "0.495"), volume=240000.0)
TAIWAN = gamma_market("1200003", "Will China invade Taiwan by end of 2026?", "china-invade-taiwan-2026", prices=("0.03", "0.97"), volume=500000.0)
PAGE_JSON = [RUSSIA, TAIWAN, FED_HOLD, FED_CUT]

BOOK_JSON = {
    "market": CONDITION,
    "asset_id": TOKEN_YES,
    "timestamp": "1789712736528",
    "bids": [{"price": "0.01", "size": "360.11"}, {"price": "0.76", "size": "1200.5"}, {"price": "0.75", "size": "88"}],
    "asks": [{"price": "0.99", "size": "51718.13"}, {"price": "0.77", "size": "76669.76"}, {"price": "0.78", "size": "190580.93"}],
    "min_order_size": "5",
    "tick_size": "0.01",
    "neg_risk": True,
    "last_trade_price": "0.760",
}
HISTORY_JSON = {"history": [{"t": 1789626610, "p": 0.735}, {"t": 1789626312, "p": 0.735}, {"t": 1789627809, "p": 0.74}, {"t": "bad", "p": 1}]}


class PolymarketCase(unittest.TestCase):
    def transport(self, **overrides):
        routes = {
            PAGE: PAGE_JSON,
            GAMMA_HOST + "/markets/1130012": RUSSIA,
            GAMMA_HOST + "/markets?condition_ids=" + CONDITION: [RUSSIA],
            GAMMA_HOST + "/markets?slug=" + RUSSIA["slug"]: [RUSSIA],
            GAMMA_HOST + "/markets?slug=nope": [],
            GAMMA_HOST + "/markets/999": (404, {}, b'{"error":"not found"}'),
            CLOB_HOST + "/book?token_id=" + TOKEN_YES: BOOK_JSON,
            CLOB_HOST + "/prices-history?market=" + TOKEN_YES + "&interval=1d&fidelity=5": HISTORY_JSON,
        }
        routes.update(overrides)
        return FakeTransport(routes)

    def polymarket(self, transport=None):
        return Polymarket(transport or self.transport(), clock=Clock("2026-09-18T06:30:00Z"))


class SearchTests(PolymarketCase):
    def test_search_fetches_one_page_by_volume_and_filters_on_question_tokens(self):
        transport = self.transport()
        rows = self.polymarket(transport).search("fed interest rates october", limit=5)
        self.assertEqual([r["id"] for r in rows], ["1200001", "1200002"])
        self.assertEqual(rows[0]["score"], 1.0)
        self.assertEqual(rows[0]["outcomes"], ["Yes", "No"])
        self.assertEqual(rows[0]["prices"], [0.48, 0.52])
        self.assertEqual(rows[0]["token_ids"], [TOKEN_YES, TOKEN_NO])
        self.assertEqual(rows[0]["liquidity"], 705727.9141)
        self.assertEqual(rows[0]["end_date"], "2026-09-30T00:00:00Z")
        call = transport.last
        self.assertEqual(call["path"], "/markets")
        self.assertEqual(call["query"], {"limit": "100", "order": "volume24hr", "ascending": "false", "active": "true", "closed": "false"})
        self.assertEqual(call["headers"]["User-Agent"], USER_AGENT)

    def test_an_empty_query_returns_the_page_in_volume_order_and_limit_applies(self):
        rows = self.polymarket().search("", limit=2)
        self.assertEqual([r["id"] for r in rows], ["1130012", "1200003"])
        self.assertEqual(self.polymarket().search("fed", limit=1)[0]["id"], "1200001")

    def test_stopwords_do_not_match(self):
        self.assertEqual(tokens("Will the Fed cut rates by 25 bps?"), ["fed", "cut", "rates", "25", "bps"])
        # A query made only of stopwords is an empty query: the page comes back in volume order.
        self.assertEqual([r["id"] for r in self.polymarket().search("will the be by", limit=1)], ["1130012"])

    def test_matches_prices_a_kalshi_title_against_the_page(self):
        found = self.polymarket().matches("Will the Fed decrease interest rates by 25 bps after the October 2026 meeting?", limit=2)
        self.assertEqual([r["id"] for r in found], ["1200002", "1200001"])
        self.assertEqual(found[0]["score"], 1.0)
        self.assertEqual(found[0]["yes_price"], 0.505)
        self.assertEqual(found[0]["token_ids"][0], TOKEN_YES)
        self.assertEqual(self.polymarket().matches("Will the Yankees win the World Series?"), [])
        # A page already in hand is reused without a request.
        transport = self.transport()
        self.polymarket(transport).matches("Fed interest rates October 2026", rows=PAGE_JSON and [market_row(m) for m in PAGE_JSON])
        self.assertEqual(transport.calls, [])


class MarketTests(PolymarketCase):
    def test_one_market_by_id_slug_or_condition_id(self):
        polymarket = self.polymarket()
        for key in ("1130012", RUSSIA["slug"], CONDITION):
            row = polymarket.market(key)
            self.assertEqual(row["id"], "1130012")
            self.assertEqual(row["condition_id"], CONDITION)
            self.assertEqual(row["prices"], [0.765, 0.235])
            self.assertEqual(row["volume_24h"], 622762.12)

    def test_an_unknown_market_is_a_data_error(self):
        with self.assertRaises(DataError):
            self.polymarket().market("999")
        with self.assertRaises(DataError):
            self.polymarket().market("nope")
        with self.assertRaises(DataError):
            self.polymarket().market("")

    def test_a_row_with_broken_fields_never_raises(self):
        broken = market_row({"id": 7, "question": "Q?", "outcomes": "not json", "outcomePrices": '["x", "0.5"]', "volume24hr": None})
        self.assertEqual(broken["outcomes"], [])
        self.assertEqual(broken["prices"], [None, 0.5])
        self.assertIsNone(broken["volume_24h"])
        self.assertEqual(broken["token_ids"], [])
        self.assertIsNone(market_row({"id": 1}))
        self.assertIsNone(market_row("junk"))


class ClobTests(PolymarketCase):
    def test_the_book_is_sorted_with_mid_and_spread(self):
        book = self.polymarket().book(TOKEN_YES)
        self.assertEqual(book["bids"][:2], [[0.76, 1200.5], [0.75, 88.0]])
        self.assertEqual(book["asks"][:2], [[0.77, 76669.76], [0.78, 190580.93]])
        self.assertEqual((book["best_bid"], book["best_ask"], book["mid"], book["spread"]), (0.76, 0.77, 0.765, 0.01))
        self.assertEqual(book["last_trade"], 0.76)
        self.assertEqual(book["tick_size"], 0.01)
        self.assertEqual(book["as_of"], "2026-09-18T06:30:00Z")

    def test_an_empty_book_has_no_mid(self):
        empty = self.polymarket(self.transport(**{CLOB_HOST + "/book?token_id=" + TOKEN_YES: {"bids": [], "asks": []}})).book(TOKEN_YES)
        self.assertEqual((empty["bids"], empty["asks"], empty["mid"], empty["spread"]), ([], [], None, None))
        with self.assertRaises(DataError):
            self.polymarket(self.transport(**{CLOB_HOST + "/book?token_id=" + TOKEN_YES: (500, {}, b"down")})).book(TOKEN_YES)

    def test_price_history_is_oldest_first_and_skips_bad_points(self):
        transport = self.transport()
        rows = self.polymarket(transport).price_history(TOKEN_YES)
        self.assertEqual(rows, [{"t": 1789626312, "p": 0.735}, {"t": 1789626610, "p": 0.735}, {"t": 1789627809, "p": 0.74}])
        self.assertEqual(transport.last["query"], {"market": TOKEN_YES, "interval": "1d", "fidelity": "5"})
        blank = self.polymarket(self.transport(**{CLOB_HOST + "/prices-history?market=" + TOKEN_YES + "&interval=1d&fidelity=5": {"history": []}}))
        self.assertEqual(blank.price_history(TOKEN_YES), [])


if __name__ == "__main__":
    unittest.main()
