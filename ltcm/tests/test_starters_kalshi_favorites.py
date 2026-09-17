"""The favorites starter, version 2: book pricing, the cluster cap, expiry, queue keeping and the
band exit, each off until its param is set. A fake kit; no network."""

from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone

from ltcm.backtest import check_code
from ltcm.strategies import STARTER_VARIANTS, STARTERS_DIR

NOW = "2026-09-17T04:10:00.000Z"
NOW_DT = datetime(2026, 9, 17, 4, 10, tzinfo=timezone.utc)

BOARD = [
    {"ticker": "KXFEDMENTION-26SEP17-TARIFF", "title": "Powell says tariff", "status": "active", "close_time": "2026-09-17T20:00:00Z", "yes_bid": "0.04", "yes_ask": "0.06", "volume_24h": "25000"},
    {"ticker": "KXFEDMENTION-26SEP17-RECESSION", "title": "Powell says recession", "status": "active", "close_time": "2026-09-17T20:00:00Z", "yes_bid": "0.03", "yes_ask": "0.05", "volume_24h": "20000"},
    {"ticker": "KXRAIN-26SEP17-PVD", "title": "Rain in Providence", "status": "active", "close_time": "2026-09-18T04:00:00Z", "yes_bid": "0.07", "yes_ask": "0.08", "volume_24h": "19000"},
    {"ticker": "KXBTCD-26SEP1714-T80000", "title": "BTC above 80,000", "status": "active", "close_time": "2026-09-17T18:00:00Z", "yes_bid": "0.05", "yes_ask": "0.07", "volume_24h": "40000"},
    {"ticker": "KXMLBGAME-26SEP17NYYBOS-NYY", "title": "Yankees", "status": "active", "close_time": "2026-09-18T02:00:00Z", "yes_bid": "0.55", "yes_ask": "0.57", "volume_24h": "90000"},
    {"ticker": "KXTHIN-26SEP17-X", "title": "thin", "status": "active", "close_time": "2026-09-17T20:00:00Z", "yes_bid": "0.02", "yes_ask": "0.05", "volume_24h": "10"},
]
BTC, RAIN, TARIFF, RECESSION = "KXBTCD-26SEP1714-T80000", "KXRAIN-26SEP17-PVD", "KXFEDMENTION-26SEP17-TARIFF", "KXFEDMENTION-26SEP17-RECESSION"

#: Version 1's output on BOARD with two resting bids, captured from the code at 6bd05fe before
#: version 2 existed. With every new param unset, version 2 must return exactly this.
V1_RATIONALE = (
    "Favorite: {ticker} ({title}) has YES at {yes:.2f} with {volume} contracts traded today and settles in {hours}h. Kalshi "
    "longshots resolve YES less often than their price implies (Bürgi, Deng and Whelan 2025), so the NO side is the favorite "
    "with the edge; resting a post-only NO bid at {price}, a cent over the best NO bid, as a maker (no fee). One position per "
    "event. Holds to settlement; wrong if this band's settled NO record returns less than the fees it saved."
)
V1_OUTPUT = {
    "intents": [
        {
            "instrument": {"asset_class": "event", "symbol": BTC, "market_id": BTC, "right": "no"},
            "side": "buy", "quantity": "15", "order_type": "limit", "limit_price": "0.94", "post_only": True,
            "rationale": V1_RATIONALE.replace("{ticker}", BTC).replace("{title}", "BTC above 80,000").replace("{yes:.2f}", "0.07")
            .replace("{volume}", "40,000").replace("{hours}", "14").replace("{price}", "0.94"),
            "holding_period_hours": 14,
        },
        {
            "instrument": {"asset_class": "event", "symbol": RAIN, "market_id": RAIN, "right": "no"},
            "side": "buy", "quantity": "16", "order_type": "limit", "limit_price": "0.92", "post_only": True,
            "rationale": V1_RATIONALE.replace("{ticker}", RAIN).replace("{title}", "Rain in Providence").replace("{yes:.2f}", "0.08")
            .replace("{volume}", "19,000").replace("{hours}", "24").replace("{price}", "0.92"),
            "holding_period_hours": 24,
        },
    ],
    "cancels": ["ord-old"],
    "notes": "4 favorites in band, 2 placed, 1 cancelled",
}
V1_LOG = ["6 markets listed, 4 in the band, 2 bid(s), 1 requoted"]
V1_ORDERS = [
    {"order_id": "ord-old", "strategy": "kalshi_favorites", "market_id": RAIN, "limit_price": "0.92", "submitted_at": "2026-09-17T02:00:00Z"},
    {"order_id": "ord-new", "strategy": "kalshi_favorites", "market_id": RECESSION, "limit_price": "0.95", "submitted_at": "2026-09-17T04:00:00Z"},
]


def load():
    spec = importlib.util.spec_from_file_location("starter_kalshi_favorites_v2", STARTERS_DIR / "kalshi_favorites.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def book(no=(), yes=()):
    """A kit.kalshi_orderbooks entry with levels in the order given (the venue sends worst first)."""
    return {"no": [(price, "10.00") for price in no], "yes": [(price, "10.00") for price in yes]}


def ago(minutes):
    return (NOW_DT - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def resting(order_id, ticker, price, minutes_old):
    return {"order_id": order_id, "strategy": "kalshi_favorites", "market_id": ticker, "limit_price": price, "submitted_at": ago(minutes_old)}


class FavKit:
    def __init__(self, board=BOARD, books=None, *, positions=(), orders=(), markets=None):
        self.context = {"now": NOW, "positions": list(positions), "open_orders": list(orders), "learning_usd": "15", "live": False}
        self.board = [dict(row) for row in board]
        self.books = dict(books or {})
        self.markets = dict(markets or {})
        self.log = []
        self.book_calls = []
        self.market_calls = []

    def say(self, text):
        self.log.append(text)

    def kalshi_markets(self, max_close_hours=36, pages=5):
        return [dict(row) for row in self.board]

    def kalshi_orderbooks(self, tickers):
        self.book_calls.append(list(tickers))
        return {t: self.books[t] for t in tickers if t in self.books}

    def kalshi_market(self, ticker):
        self.market_calls.append(ticker)
        return self.markets.get(ticker)


def bids(out):
    return {i["instrument"]["market_id"]: i for i in out["intents"]}


class VersionOneTests(unittest.TestCase):
    def test_with_every_new_param_unset_the_output_is_version_one_byte_for_byte(self):
        for params in ({}, {"book_pricing": False, "keep_queue": False, "band_exit": False, "max_open_per_cluster": None, "expire_seconds": None}):
            kit = FavKit(orders=V1_ORDERS)
            out = load().decide(kit, params)
            self.assertEqual(out, V1_OUTPUT)
            self.assertEqual(list(out["intents"][0]), ["instrument", "side", "quantity", "order_type", "limit_price", "post_only", "rationale", "holding_period_hours"])
            self.assertEqual(kit.log, V1_LOG)
            self.assertEqual((kit.book_calls, kit.market_calls), ([], []), "no book is read and no market is looked up")

    def test_the_starter_passes_the_backtest_code_screen(self):
        check_code((STARTERS_DIR / "kalshi_favorites.py").read_text(encoding="utf-8"))


class BookPricingTests(unittest.TestCase):
    def test_levels_arriving_worst_first_still_price_off_the_best_level(self):
        # Read as sent, index 0 would be a 0.01 NO bid: YES at 0.99, far out of the band.
        kit = FavKit(books={BTC: book(no=["0.0100", "0.9000", "0.9300"], yes=["0.0100", "0.0300", "0.0500"])})
        out = load().decide(kit, {"book_pricing": True})
        self.assertEqual(list(bids(out)), [BTC], "markets without a book are skipped")
        bid = bids(out)[BTC]
        self.assertEqual((bid["limit_price"], bid["post_only"], bid["instrument"]["right"]), ("0.94", True, "no"))
        self.assertIn("on the live book (NO 0.93/0.95)", bid["rationale"])
        self.assertIn("0 bid(s) joined the best NO bid", kit.log[-1], "0.94 is a tick over the best bid")

    def test_a_one_tick_spread_joins_the_best_bid(self):
        kit = FavKit(books={RAIN: book(no=["0.9200"], yes=["0.0700"])})
        bid = bids(load().decide(kit, {"book_pricing": True}))[RAIN]
        self.assertEqual(bid["limit_price"], "0.92", "NO ask 0.93: one tick over the bid would take")
        self.assertIn("on the live book (NO 0.92/0.93)", bid["rationale"])
        self.assertIn("1 bid(s) joined the best NO bid", kit.log[-1])

    def test_a_missing_book_means_no_intent_and_no_fallback_to_the_row(self):
        kit = FavKit(books={})
        out = load().decide(kit, {"book_pricing": True})
        self.assertEqual(out["intents"], [])
        self.assertEqual(kit.book_calls, [[BTC, TARIFF, RECESSION, RAIN]], "one read, the band's candidates by volume")
        self.assertIn("4 no book", kit.log[-1])

    def test_the_band_is_checked_again_on_the_books_yes_ask(self):
        kit = FavKit(books={BTC: book(no=["0.8500"], yes=["0.1300"]), RAIN: book(no=["0.9200"], yes=["0.0700"])})
        out = load().decide(kit, {"book_pricing": True})
        self.assertEqual(list(bids(out)), [RAIN], "the row said 0.07; the book says YES 0.15, out of the band")
        self.assertIn("1 book crossed or out of band", kit.log[-1])

    def test_a_crossed_book_is_skipped(self):
        kit = FavKit(books={BTC: book(no=["0.9500"], yes=["0.0600"])})
        self.assertEqual(load().decide(kit, {"book_pricing": True})["intents"], [])
        self.assertIn("1 book crossed or out of band", kit.log[-1], "YES bid 0.06 and NO bid 0.95 add past a dollar")

    def test_the_tick_comes_from_the_markets_price_ranges_on_the_yes_scale(self):
        board = [dict(BOARD[3], price_ranges=[
            {"start": "0.0000", "end": "0.1000", "step": "0.0010"},
            {"start": "0.1000", "end": "0.9000", "step": "0.0100"},
            {"start": "0.9000", "end": "1.0000", "step": "0.0010"},
        ])]
        kit = FavKit(board, books={BTC: book(no=["0.9350"], yes=["0.0600"])})
        bid = bids(load().decide(kit, {"book_pricing": True}))[BTC]
        self.assertEqual(bid["limit_price"], "0.9360", "YES 0.065 sits in the tenth-of-a-cent band")

    def test_a_taker_takes_the_books_no_ask_and_skips_a_book_with_no_yes_bid(self):
        kit = FavKit(books={BTC: book(no=["0.9300"], yes=["0.0400", "0.0500"]), RAIN: book(no=["0.9200"])})
        out = load().decide(kit, {"book_pricing": True, "maker": False})
        self.assertEqual(list(bids(out)), [BTC])
        self.assertEqual(bids(out)[BTC]["limit_price"], "0.95")
        self.assertNotIn("post_only", bids(out)[BTC])
        self.assertNotIn(RAIN, bids(out), "no YES bid: the only NO ask is 1.00, past 0.99")


class RestingOrderTests(unittest.TestCase):
    def test_band_exit_cancels_a_bid_once_the_yes_bid_reaches_the_band_top_plus_two_cents(self):
        orders = [resting("ord-rain", RAIN, "0.92", 10)]
        kit = FavKit(orders=orders, books={RAIN: book(no=["0.8700"], yes=["0.1200"])})
        out = load().decide(kit, {"band_exit": True})
        self.assertEqual(out["cancels"], ["ord-rain"])
        self.assertIn("cancelled: 1 band exit", kit.log[-1])
        self.assertEqual(kit.book_calls, [[RAIN]], "only the resting bid's book is read")
        kit = FavKit(orders=orders, books={RAIN: book(no=["0.8800"], yes=["0.1100"])})
        self.assertEqual(load().decide(kit, {"band_exit": True})["cancels"], [], "YES bid 0.11 is under 0.12")
        self.assertEqual(load().decide(FavKit(orders=orders, books={RAIN: book(no=["0.87"], yes=["0.12"])}), {})["cancels"], [], "off by default")

    def test_keep_queue_keeps_a_stale_bid_that_is_still_the_best(self):
        stale_at_best = [resting("ord-rain", RAIN, "0.92", 180)]
        kit = FavKit(orders=stale_at_best, books={RAIN: book(no=["0.9200"], yes=["0.0700"])})
        out = load().decide(kit, {"keep_queue": True})
        self.assertEqual(out["cancels"], [])
        self.assertNotIn(RAIN, bids(out), "its event is held by the kept bid")
        self.assertEqual(load().decide(FavKit(orders=stale_at_best), {})["cancels"], ["ord-rain"], "version 1 requotes it")

    def test_keep_queue_requotes_a_stale_bid_behind_the_best_and_any_bid_two_ticks_behind(self):
        one_behind = {RAIN: book(no=["0.9300"], yes=["0.0600"])}
        self.assertEqual(load().decide(FavKit(orders=[resting("o", RAIN, "0.92", 180)], books=one_behind), {"keep_queue": True})["cancels"], ["o"])
        self.assertEqual(load().decide(FavKit(orders=[resting("o", RAIN, "0.92", 5)], books=one_behind), {"keep_queue": True})["cancels"], [], "young and one tick behind: kept")
        two_behind = {RAIN: book(no=["0.9400"], yes=["0.0500"])}
        kit = FavKit(orders=[resting("o", RAIN, "0.92", 5)], books=two_behind)
        self.assertEqual(load().decide(kit, {"keep_queue": True})["cancels"], ["o"])
        self.assertIn("cancelled: 1 behind", kit.log[-1])

    def test_keep_queue_never_keeps_a_stale_bid_into_the_final_window(self):
        # Version 1 pulls a stale bid and does not replace it once its market is inside min_hours;
        # until the review of Sept 17, 2026 keep_queue kept one that was still the best to the close.
        closing = dict(BOARD[0], ticker="KXCPI-26SEP17-T3", title="CPI", close_time="2026-09-17T04:40:00Z")
        books = {"KXCPI-26SEP17-T3": book(no=["0.9400"], yes=["0.0400"])}
        stale = [resting("ord-cpi", "KXCPI-26SEP17-T3", "0.94", 180)]
        self.assertEqual(load().decide(FavKit(BOARD + [closing], orders=stale, books=books), {})["cancels"], ["ord-cpi"], "version 1")
        kit = FavKit(BOARD + [closing], orders=stale, books=books)
        out = load().decide(kit, {"keep_queue": True})
        self.assertEqual(out["cancels"], ["ord-cpi"])
        self.assertIn("cancelled: 1 final window", kit.log[-1])
        self.assertNotIn("KXCPI-26SEP17-T3", bids(out))
        young = [resting("ord-cpi", "KXCPI-26SEP17-T3", "0.94", 5)]
        self.assertEqual(load().decide(FavKit(BOARD + [closing], orders=young, books=books), {"keep_queue": True})["cancels"], [], "a young bid, as in version 1")
        far = dict(closing, close_time="2026-09-17T20:00:00Z")
        self.assertEqual(load().decide(FavKit(BOARD + [far], orders=stale, books=books), {"keep_queue": True})["cancels"], [], "outside the window the best bid keeps its place")

    def test_keep_queue_without_a_book_falls_back_to_the_age_rule(self):
        self.assertEqual(load().decide(FavKit(orders=[resting("o", RAIN, "0.92", 180)]), {"keep_queue": True})["cancels"], ["o"])
        self.assertEqual(load().decide(FavKit(orders=[resting("o", RAIN, "0.92", 5)]), {"keep_queue": True})["cancels"], [])


class ClusterTests(unittest.TestCase):
    def test_the_cluster_key_groups_roots_and_splits_by_close_hour(self):
        module = load()
        close = datetime(2026, 9, 17, 18, 0, tzinfo=timezone.utc)
        self.assertEqual(module._cluster("KXBTCD-26SEP1714-T80000", close), ("crypto", "2026-09-17T18"))
        self.assertEqual(module._cluster("KXETHD-26SEP1714-T4000", close), module._cluster("KXBTCD-26SEP1714-T80000", close))
        self.assertEqual(module._cluster("KXDOGE-26SEP1714-B1", close)[0], "crypto")
        self.assertEqual(module._cluster("KXWTI-26SEP17-T70", close)[0], "commod")
        self.assertEqual(module._cluster("KXHIGHNY-26SEP17-B81.5", close)[0], "weather")
        self.assertEqual(module._cluster("KXFEDMENTION-26SEP17-TARIFF", close)[0], "KXFEDMENTION")
        self.assertNotEqual(module._cluster("KXBTCD-26SEP1714-T80000", close), module._cluster("KXBTCD-26SEP1715-T80000", close + timedelta(hours=1)))
        self.assertEqual(module._cluster("KXBTCD-26SEP1714-T80000", None), ("crypto", None))

    def test_the_cluster_cap_counts_resting_bids(self):
        eth = {"ticker": "KXETHD-26SEP1714-T4000", "title": "ETH above 4,000", "status": "active", "close_time": "2026-09-17T18:00:00Z", "yes_bid": "0.30", "yes_ask": "0.32", "volume_24h": "9000"}
        orders = [resting("ord-eth", "KXETHD-26SEP1714-T4000", "0.68", 5)]
        kit = FavKit(BOARD + [eth], orders=orders)
        out = load().decide(kit, {"max_open_per_cluster": 1})
        self.assertEqual(out["cancels"], [])
        self.assertNotIn(BTC, bids(out), "the ETH bid closing the same hour fills the crypto cluster")
        self.assertEqual(list(bids(out)), [TARIFF, RAIN])
        self.assertIn("1 cluster cap", kit.log[-1])
        self.assertEqual(kit.book_calls, [], "no book is needed for the cap")
        self.assertIn(BTC, bids(load().decide(FavKit(BOARD + [eth], orders=orders), {"max_open_per_cluster": 2})))

    def test_new_bids_in_one_run_count_toward_the_cap(self):
        other = dict(BOARD[3], ticker="KXSOLD-26SEP1714-T200", title="SOL above 200", volume_24h="30000")
        out = load().decide(FavKit(BOARD + [other]), {"max_open_per_cluster": 1, "max_new": 6})
        self.assertIn(BTC, bids(out))
        self.assertNotIn("KXSOLD-26SEP1714-T200", bids(out))

    def test_a_held_market_missing_from_the_listing_is_looked_up_and_an_unknown_close_blocks_its_group(self):
        positions = [{"market_id": "KXSOLD-26SEP1614-T200", "asset_class": "event", "quantity": "10"}]
        kit = FavKit(positions=positions, markets={"KXSOLD-26SEP1614-T200": {"close_time": "2026-09-16T18:00:00Z"}})
        out = load().decide(kit, {"max_open_per_cluster": 1})
        self.assertEqual(kit.market_calls, ["KXSOLD-26SEP1614-T200"])
        self.assertIn(BTC, bids(out), "yesterday's hour is another cluster")
        kit = FavKit(positions=positions, markets={})
        self.assertNotIn(BTC, bids(load().decide(kit, {"max_open_per_cluster": 1})), "a close that cannot be read counts against every crypto hour")


class ExpiryTests(unittest.TestCase):
    def test_expires_at_is_the_earlier_of_the_horizon_and_close_minus_min_hours(self):
        soon = dict(BOARD[0], ticker="KXCPI-26SEP17-T3", title="CPI", close_time="2026-09-17T06:00:00Z", volume_24h="50000")
        board = BOARD + [soon]
        out = load().decide(FavKit(board), {"expire_seconds": 5400, "min_hours": 1.5, "max_new": 6})
        closes = {row["ticker"]: row["close_time"] for row in board}
        self.assertEqual(sorted(bids(out)), sorted(["KXCPI-26SEP17-T3", BTC, TARIFF, RAIN]))
        for intent in out["intents"]:
            ticker = intent["instrument"]["market_id"]
            expires = datetime.strptime(intent["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            close = datetime.strptime(closes[ticker], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            self.assertLessEqual(expires, close - timedelta(hours=1.5), ticker)
            self.assertLessEqual(expires, NOW_DT + timedelta(seconds=5400), ticker)
        self.assertEqual(bids(out)["KXCPI-26SEP17-T3"]["expires_at"], "2026-09-17T04:30:00Z", "close 06:00 less 1.5h")
        self.assertEqual(bids(out)[BTC]["expires_at"], "2026-09-17T05:40:00Z", "now plus 90 minutes")
        self.assertIn("expiring 05:40Z", bids(out)[BTC]["rationale"])

    def test_a_bid_that_would_live_under_two_minutes_is_not_placed(self):
        edge = dict(BOARD[0], ticker="KXCPI-26SEP17-T3", title="CPI", close_time="2026-09-17T05:41:30Z", volume_24h="50000")
        kit = FavKit([edge])
        out = load().decide(kit, {"expire_seconds": 5400, "min_hours": 1.5})
        self.assertEqual(out["intents"], [], "05:41:30 less 1.5h is 90 seconds away")
        self.assertIn("1 final window", kit.log[-1])

    def test_a_resting_bid_inside_the_final_window_is_cancelled(self):
        closing = dict(BOARD[0], ticker="KXCPI-26SEP17-T3", title="CPI", close_time="2026-09-17T05:30:00Z")
        kit = FavKit(BOARD + [closing], orders=[resting("ord-cpi", "KXCPI-26SEP17-T3", "0.94", 5)])
        out = load().decide(kit, {"expire_seconds": 5400, "min_hours": 1.5})
        self.assertEqual(out["cancels"], ["ord-cpi"])
        self.assertIn("cancelled: 1 final window", kit.log[-1])
        self.assertEqual(load().decide(FavKit(BOARD + [closing], orders=[resting("ord-cpi", "KXCPI-26SEP17-T3", "0.94", 5)]), {"min_hours": 1.5})["cancels"], [])

    def test_no_expiry_key_without_expire_seconds(self):
        self.assertTrue(all("expires_at" not in i for i in load().decide(FavKit(), {"book_pricing": False})["intents"]))


class StartingParamsTests(unittest.TestCase):
    #: The shadow starting params in the Sept 17, 2026 build plan (mullins-5, -6, -8).
    PLAN = {"book_pricing": True, "keep_queue": True, "band_exit": True, "max_open_per_cluster": 2, "expire_seconds": 5400, "yes_min": 0.04,
            "yes_max": 0.10, "min_hours": 1.5, "max_hours": 48, "min_volume_24h": 1000, "max_new": 6, "max_open_per_series": 3,
            "requote_seconds": 3600, "pages": 20}

    def test_the_plans_shadow_params_run_end_to_end(self):
        books = {BTC: book(no=["0.9000", "0.9300"], yes=["0.0400", "0.0500"]), TARIFF: book(no=["0.9400"], yes=["0.0400"]), RAIN: book(no=["0.9200"], yes=["0.0700"])}
        orders = [resting("ord-rec", RECESSION, "0.95", 50)]
        kit = FavKit(books=books, orders=orders)
        out = load().decide(kit, dict(self.PLAN))
        self.assertEqual(out["cancels"], [], "the resting bid has no book and 50 minutes is under the hour")
        self.assertEqual(sorted(bids(out)), sorted([BTC, RAIN]), "TARIFF shares the event with the resting RECESSION bid")
        for intent in out["intents"]:
            self.assertTrue(intent["post_only"])
            self.assertIn("expires_at", intent)
        self.assertEqual(len(kit.book_calls), 1)
        self.assertLessEqual(len(kit.book_calls[0]), 300)
        self.assertEqual(kit.book_calls[0][0], RECESSION, "resting bids' books come first")

    def test_the_family_variants_follow_the_plan(self):
        variants = STARTER_VARIANTS["kalshi"]
        self.assertNotIn({"yes_min": 0.10, "yes_max": 0.25, "max_hours": 24}, variants)
        for row in ({"yes_max": 0.07}, {"min_hours": 3}, {"maker": False, "yes_max": 0.07}, {"max_open_per_cluster": 1}):
            self.assertIn(row, variants)
        defaults = load().DEFAULTS
        for row in variants:
            self.assertTrue(set(row) <= set(defaults), row)


if __name__ == "__main__":
    unittest.main()
