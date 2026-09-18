"""The arena's forward-only house starters (Sept 18, 2026): temperature brackets from ensembles,
Kalshi against Polymarket, and funding fades on the perps. Fake kits; no network."""

from __future__ import annotations

import importlib.util
import unittest

from ltcm.backtest import check_code
from ltcm.strategies import STARTERS_DIR

NOW = "2026-09-18T12:00:00.000Z"


def load(name):
    spec = importlib.util.spec_from_file_location(f"starter_{name}", STARTERS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BaseKit:
    def __init__(self, **context):
        self.context = {"now": NOW, "positions": [], "open_orders": [], "learning_usd": "40", "live": True, "equity_usd": "500",
                        "fee_rates": {"coinbase": {"maker": "0.005", "taker": "0.009", "future_contract": "0.20", "age_seconds": 1}}, **context}
        self.log = []

    def say(self, text):
        self.log.append(text)


class TempsKit(BaseKit):
    def __init__(self, members, markets, **context):
        super().__init__(**context)
        self.members, self.markets = members, markets

    def weather_cities(self):
        return [{"name": "New York", "series": "KXHIGHNY", "station": "KNYC"}]

    def ensemble(self, city, days=3):
        m = sorted(self.members)
        return {"days": [{"date": "2026-09-18", "members": m, "mean": sum(m) / len(m), "sd": 1.2, "p10": m[len(m) // 10], "p50": m[len(m) // 2], "p90": m[-len(m) // 10], "n": len(m)}]}

    def kalshi_series(self, series, limit=1000, status="open"):
        return list(self.markets)

    def kalshi_market(self, ticker):
        return next((m for m in self.markets if m["ticker"] == ticker), None)


def bracket_market(ticker, label, yes_bid, yes_ask):
    return {"ticker": ticker, "yes_sub_title": label, "close_time": "2026-09-19T03:00:00Z", "status": "open", "yes_bid": yes_bid, "yes_ask": yes_ask}


class TempsEnsembleTests(unittest.TestCase):
    def test_the_bracket_the_members_favor_is_bought_where_the_market_is_cheap(self):
        module = load("temps_ensemble")
        check_code(open(STARTERS_DIR / "temps_ensemble.py").read())
        members = [80.6, 81.2, 81.4, 81.9, 82.1, 82.4, 82.6, 83.0, 81.7, 82.2] * 5
        markets = [
            bracket_market("KXHIGHNY-26SEP18-B81.5", "81° to 82°", 0.30, 0.33),   # members put ~60% here
            bracket_market("KXHIGHNY-26SEP18-B83.5", "83° or above", 0.20, 0.24),  # ~0%
            bracket_market("KXHIGHNY-26SEP18-B79.5", "79° or below", 0.02, 0.04),
        ]
        out = module.decide(TempsKit(members, markets), {"min_edge": 0.02, "weight": 1.0})
        intents = out["intents"]
        self.assertEqual(len(intents), 1, "one position per event: the day's brackets settle together")
        first = intents[0]
        self.assertEqual((first["instrument"]["market_id"], first["instrument"]["right"]), ("KXHIGHNY-26SEP18-B81.5", "yes"), "the best edge: 60% of members, market at 0.33")
        # Alone, a tail bracket the market prices rich is a NO: a fifth of the members round to 83
        # or more (82.6 settles as 83), the market says over a third.
        rich = [bracket_market("KXHIGHNY-26SEP18-B83.5", "83° or above", 0.35, 0.38)]
        tail = module.decide(TempsKit(members, rich), {"min_edge": 0.02, "weight": 1.0})["intents"]
        self.assertEqual((tail[0]["instrument"]["market_id"], tail[0]["instrument"]["right"]), ("KXHIGHNY-26SEP18-B83.5", "no"))
        self.assertEqual(module.decide(TempsKit(members, markets[1:2]), {"min_edge": 0.02, "weight": 1.0})["intents"], [], "at 0.22 the market agrees with the members")
        self.assertEqual(module.decide(TempsKit(members, markets[2:]), {"min_edge": 0.02, "weight": 1.0})["intents"], [], "a 0.04 contract has no edge to buy NO at 0.98")
        self.assertEqual(first["side"], "buy")
        self.assertIn("ensemble members", first["rationale"])
        self.assertEqual(first["quantity"], str(int(40 / float(first["limit_price"]))))

    def test_a_held_market_and_a_wide_band_are_left_alone(self):
        module = load("temps_ensemble")
        members = [81.0] * 30
        markets = [bracket_market("KXHIGHNY-26SEP18-B81.5", "81° to 82°", 0.90, 0.93)]
        kit = TempsKit(members, markets, positions=[{"market_id": "KXHIGHNY-26SEP18-B81.5"}])
        self.assertEqual(module.decide(kit, {})["intents"], [])
        self.assertEqual(module.decide(TempsKit(members, markets), {"min_edge": 0.10})["intents"], [], "0.93 for a sure thing is not 10 cents of edge")

    def test_maker_rests_inside_the_spread(self):
        module = load("temps_ensemble")
        members = [81.0] * 30
        markets = [bracket_market("KXHIGHNY-26SEP18-B81.5", "81° to 82°", 0.50, 0.60)]
        intents = module.decide(TempsKit(members, markets), {"maker": True, "min_edge": 0.0, "weight": 1.0, "shrink": 0.0})["intents"]
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["limit_price"], "0.51")
        self.assertTrue(intents[0]["post_only"])


class PolyKit(BaseKit):
    def __init__(self, poly, board, books=None, **context):
        super().__init__(**context)
        self.poly, self.board, self.books = poly, board, books or {}

    def polymarket(self, query="", limit=20):
        return list(self.poly)

    def kalshi_markets(self, max_close_hours=36, pages=5):
        return list(self.board)

    def kalshi_series(self, series, limit=1000, status="open"):
        return [m for m in self.board if str(m["ticker"]).startswith(str(series) + "-")]

    def kalshi_orderbooks(self, tickers):
        return {t: self.books[t] for t in tickers if t in self.books}


POLY = [
    {"question": "Will the Fed cut interest rates at the October 2026 meeting?", "outcomes": ["Yes", "No"], "prices": [0.72, 0.28], "volume_24h": 250000, "end_date": "2026-10-28T00:00:00Z"},
    {"question": "Will Bitcoin be above $80,000 on September 20?", "outcomes": ["Yes", "No"], "prices": [0.35, 0.65], "volume_24h": 90000, "end_date": "2026-09-20T12:00:00Z"},
]
BOARD = [
    {"ticker": "KXFEDDECISION-26OCT-C25", "title": "Will the Fed cut interest rates at its October 2026 meeting?", "close_time": "2026-10-28T18:00:00Z", "volume_24h": 40000, "yes_bid": 0.60, "yes_ask": 0.62},
    {"ticker": "KXBTC-26SEP20-T80000", "title": "Will Bitcoin be above $80,000 on September 20?", "close_time": "2026-09-20T14:00:00Z", "volume_24h": 30000, "yes_bid": 0.45, "yes_ask": 0.47},
    {"ticker": "KXBTC-26SEP20-T90000", "title": "Will Bitcoin be above $90,000 on September 20?", "close_time": "2026-09-20T14:00:00Z", "volume_24h": 30000, "yes_bid": 0.05, "yes_ask": 0.07},
    {"ticker": "KXNFLGAME-26SEP20-KC", "title": "Will the Chiefs beat the Ravens?", "close_time": "2026-09-20T23:00:00Z", "volume_24h": 90000, "yes_bid": 0.55, "yes_ask": 0.57},
]


class PolyCrossTests(unittest.TestCase):
    def test_kalshi_is_bought_on_the_side_polymarket_says_is_cheap(self):
        module = load("poly_cross")
        check_code(open(STARTERS_DIR / "poly_cross.py").read())
        out = module.decide(PolyKit(POLY, BOARD), {"min_edge": 0.04, "max_hours": 2000})
        by = {i["instrument"]["market_id"]: i for i in out["intents"]}
        self.assertEqual(by["KXFEDDECISION-26OCT-C25"]["instrument"]["right"], "yes", "0.72 on Polymarket, 0.62 on Kalshi")
        self.assertEqual(by["KXBTC-26SEP20-T80000"]["instrument"]["right"], "no", "0.35 on Polymarket, Kalshi's NO at 0.55")
        self.assertNotIn("KXBTC-26SEP20-T90000", by, "90,000 is not in any Polymarket question")
        self.assertNotIn("KXNFLGAME-26SEP20-KC", by, "no Polymarket match")
        self.assertIn("Polymarket prices", by["KXFEDDECISION-26OCT-C25"]["rationale"])

    def test_a_small_gap_a_held_event_and_a_thin_market_are_skipped(self):
        module = load("poly_cross")
        self.assertEqual(module.decide(PolyKit(POLY, BOARD), {"min_edge": 0.20, "max_hours": 2000})["intents"], [])
        held = PolyKit(POLY, BOARD, positions=[{"market_id": "KXFEDDECISION-26OCT-C25"}])
        ids = [i["instrument"]["market_id"] for i in module.decide(held, {"min_edge": 0.04, "max_hours": 2000})["intents"]]
        self.assertNotIn("KXFEDDECISION-26OCT-C25", ids)
        thin = module.decide(PolyKit(POLY, BOARD), {"min_edge": 0.04, "max_hours": 2000, "min_volume_24h": 50000})["intents"]
        self.assertEqual(thin, [], "both matched Kalshi markets trade under $50,000 a day")

    def test_live_books_price_the_order_and_a_maker_rests_inside(self):
        module = load("poly_cross")
        books = {"KXFEDDECISION-26OCT-C25": {"yes_bid": 0.58, "yes_ask": 0.66}}
        out = module.decide(PolyKit(POLY, BOARD[:1], books), {"min_edge": 0.04, "max_hours": 2000, "maker": True})
        self.assertEqual(out["intents"][0]["limit_price"], "0.59")
        self.assertTrue(out["intents"][0]["post_only"])


class FundingKit(BaseKit):
    def __init__(self, snap, quotes, **context):
        super().__init__(**context)
        self.snap, self.quotes = snap, quotes

    def derivs(self, symbols=("BTC", "ETH", "SOL")):
        return list(self.snap)

    def futures(self, root=None):
        return [
            {"symbol": "ETP-20DEC30-CDE", "root": "ETH", "price": 2444.0, "contract_size": 0.1, "contract_usd": 244.4, "perpetual": True, "volume_usd": 110e6, "quote_increment": 0.5},
            {"symbol": "SLP-20DEC30-CDE", "root": "SOL", "price": 140.0, "contract_size": 1, "contract_usd": 140.0, "perpetual": True, "volume_usd": 20e6, "quote_increment": 0.01},
        ]

    def quote(self, symbol, asset_class="crypto", venue="coinbase"):
        return self.quotes.get(symbol) or {}


class PerpFundingTests(unittest.TestCase):
    def test_crowded_longs_are_shorted_and_negative_funding_is_bought(self):
        module = load("perp_funding")
        check_code(open(STARTERS_DIR / "perp_funding.py").read())
        snap = [
            {"symbol": "ETH", "funding_z": 2.6, "okx": {"rate": 0.0005}, "hyperliquid": {"rate": 0.00006}, "dvol": 60.0},
            {"symbol": "SOL", "funding_z": -2.4, "okx": {"rate": -0.0004}, "dvol": None},
        ]
        quotes = {"ETP-20DEC30-CDE": {"bid": 2444.0, "ask": 2444.5}, "SLP-20DEC30-CDE": {"bid": 140.00, "ask": 140.02}}
        out = module.decide(FundingKit(snap, quotes), {"max_intents": 2})
        by = {i["instrument"]["symbol"]: i for i in out["intents"]}
        self.assertEqual(by["ETP-20DEC30-CDE"]["side"], "sell")
        self.assertEqual(by["ETP-20DEC30-CDE"]["limit_price"], "2443.5", "a tick under the bid")
        self.assertLess(float(by["ETP-20DEC30-CDE"]["target_price"]), 2443.5)
        self.assertGreater(float(by["ETP-20DEC30-CDE"]["stop_price"]), 2443.5)
        self.assertEqual(by["SLP-20DEC30-CDE"]["side"], "buy")
        self.assertIn("standard deviations", by["ETP-20DEC30-CDE"]["rationale"])

    def test_quiet_funding_a_held_contract_and_a_hurdle_stop_the_entry(self):
        module = load("perp_funding")
        quotes = {"ETP-20DEC30-CDE": {"bid": 2444.0, "ask": 2444.5}}
        calm = [{"symbol": "ETH", "funding_z": 0.4, "okx": {"rate": 0.0001}, "dvol": 60.0}]
        self.assertEqual(module.decide(FundingKit(calm, quotes), {})["intents"], [])
        hot = [{"symbol": "ETH", "funding_z": 3.0, "okx": {"rate": 0.0009}, "dvol": 60.0}]
        held = FundingKit(hot, quotes, positions=[{"symbol": "ETP-20DEC30-CDE", "asset_class": "future", "quantity": "-1"}])
        self.assertEqual(module.decide(held, {})["intents"], [])
        wide = {"ETP-20DEC30-CDE": {"bid": 2400.0, "ask": 2450.0}}
        self.assertEqual(module.decide(FundingKit(hot, wide), {})["intents"], [], "a 2% spread is over the target move")


if __name__ == "__main__":
    unittest.main()
