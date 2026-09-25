"""K2's capacity study (`scripts/kalshi_capacity.py`) reads what it says it reads and does the arithmetic it says.

docs/goals/LTCM_KALSHI_SCALE.md, workstream K2 (Sept 25, 2026). The box snippet runs here against a throwaway
state directory: the families' orders with their fills (the House's `source: dust` rows are not fills),
cancels, rejections and settlements, an order placed before the window left out, a positive family with no
order kept with an empty book. The fill curve is checked on hand-made prints (at the bid, through it, above
it, from either side, block trades) and on public responses recorded from Kalshi on Sept 25, 2026
(`league/tests/fixtures/kalshi_capacity_public.json`: one weather market's prints, two MLB totals books
and the open markets of their series), then halving, the envelope, the totals and a family with no orders.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from league.ledger import Ledger
from league.tests.fakes import Clock
from scripts import kalshi_capacity as kc
from scripts.floor_watch import normalize_since

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kalshi_capacity_public.json"


def _instrument(market, right="no", venue="kalshi"):
    return {"asset_class": "event", "market_id": market, "symbol": market, "right": right, "venue": venue, "multiplier": "1"}


def _epoch(at):
    return datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()


def _order(book, oid, market, agent, status, *, right="no", limit="0.90", quantity="10", post_only=True, submitted_at=None):
    return {"book": book, "order_id": oid, "instrument": _instrument(market, right, book), "side": "buy", "limit_price": limit,
            "reference_price": limit, "quantity": quantity, "post_only": post_only, "liquidity": "maker" if post_only else "taker",
            "status": status, "submitted_at": submitted_at, "shares": [{"agent": agent, "quantity": quantity}]}


class TheBoxSnippet(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock()
        self.ledger = Ledger(self.root / "ledger.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def run_snippet(self, since, until="", board=None, extra=""):
        (self.root / "health.json").write_text(json.dumps({"at": "t", "release": "r"}), encoding="utf-8")
        (self.root / "allocator-board.json").write_text(json.dumps(board or {}), encoding="utf-8")
        done = subprocess.run([sys.executable, "-c", kc.BOX_SNIPPET, since, until, str(self.root), extra],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return json.loads(done.stdout.strip().splitlines()[-1])

    BOARD = {"at": "2026-09-25T06:03:51Z", "envelope": {"kalshi": {"capital_usd": "546.83", "committed_usd": "109.23"}},
             "agents": {"mullins-1": {"venue": "kalshi", "band": "probe", "family": "weather-favorites", "stake_usd": "10"}},
             "families": {"kalshi": {
                 "weather-favorites": {"state": "unproven", "proven": False, "n": 24, "mean_log": 0.0076, "edge_per_dollar": 0.0078,
                                       "stake_usd": "10", "members_living": 2, "capacity": {"size_usd": 2.0}},
                 "sports-quiet": {"state": "proven", "proven": True, "n": 30, "mean_log": 0.2, "edge_per_dollar": 0.2,
                                  "stake_usd": "30", "capacity": {"size_usd": 6.0}},
                 "crypto-15m-lab-x": {"state": "unproven", "proven": False, "n": 60, "mean_log": -0.02}}}}

    def test_orders_fills_cancels_settlements_and_wakes_by_family(self):
        for agent, family in (("mullins-1", "weather-favorites"), ("mullins-2", "weather-favorites"),
                              ("huang-9", "crypto-15m-lab-x"), ("meriwether-5", "sports-quiet")):
            self.ledger.append("agent.born", {"venue": "kalshi", "family": family}, agent=agent)
        market = "KXHIGHNY-26SEP10-T70"
        # An order placed before the window: its later rows fall inside it, and it is not the window's.
        old = self.ledger.append("ops.started", {}).at
        self.ledger.append("book.order", _order("kalshi", "o-old", market, "mullins-1", "new", submitted_at=old), agent="house")
        self.clock.advance(60)
        since = normalize_since(self.ledger.append("ops.started", {}).at)
        self.clock.advance(1)
        self.ledger.append("book.order", _order("kalshi", "o-old", market, "mullins-1", "filled", submitted_at=old), agent="house")
        placed = self.ledger.append("book.order", _order("kalshi", "o1", market, "mullins-1", "new"), agent="house")
        self.ledger.append("book.order", _order("kalshi", "o1", market, "mullins-1", "accepted"), agent="house")
        self.clock.advance(600)
        filled = self.ledger.append("book.fill", {"book": "kalshi", "order_id": "o1", "quantity": "4", "price": "0.9", "cash_delta": "-3.6",
                                                  "liquidity": "maker", "side": "buy", "source": "venue",
                                                  "instrument": _instrument(market)}, agent="mullins-1")
        self.ledger.append("book.fill", {"book": "kalshi", "order_id": "o1", "quantity": "3", "cash_delta": "-0.0003", "source": "dust",
                                         "instrument": None}, agent="house")
        self.clock.advance(300)
        self.ledger.append("book.order", _order("kalshi", "o1", market, "mullins-1", "cancelled"), agent="house")
        self.ledger.append("book.cancel", {"book": "kalshi", "order_id": "o1"}, agent="mullins-1")
        game = "KXMLBTOTAL-26SEP101905NYYBOS-9"
        for status in ("new", "accepted", "filled"):
            self.ledger.append("book.order", _order("kalshi-shadow", "o2", game, "mullins-2", status, right="no", limit="0.55",
                                                    quantity="5", post_only=False), agent="house")
        self.ledger.append("book.fill", {"book": "kalshi-shadow", "order_id": "o2", "quantity": "5", "price": "0.55", "liquidity": "taker",
                                         "side": "buy", "source": "venue", "instrument": _instrument(game, "no", "kalshi-shadow")},
                           agent="mullins-2")
        for status in ("new", "rejected"):
            self.ledger.append("book.order", _order("kalshi-shadow", "o3", game, "mullins-2", status), agent="house")
        self.ledger.append("book.order", _order("kalshi", "o4", "KXBTC15M-26SEP100030-30", "huang-9", "new", right="yes"), agent="house")
        self.clock.advance(3600)
        settled = self.ledger.append("book.settle", {"book": "kalshi", "pnl": "0.40", "cost": "3.60", "payout": "4.00", "quantity": "4",
                                                     "instrument": _instrument(market)}, agent="mullins-1")
        self.ledger.append("agent.woke", {"book": "kalshi", "offered": 12, "intents": 1, "ok": True}, agent="mullins-1")
        self.ledger.append("agent.woke", {"book": "kalshi-shadow", "offered": 30, "intents": 0, "ok": True}, agent="mullins-2")

        out = self.run_snippet(since, board=self.BOARD)
        self.assertEqual(set(out["families"]), {"weather-favorites", "sports-quiet"}, "the proven and the positive families, not the negative")
        self.assertEqual(out["envelope"], {"capital_usd": "546.83", "committed_usd": "109.23"})
        weather = out["families"]["weather-favorites"]
        orders = {row[kc.ORDER_FIELDS.index("status")]: dict(zip(kc.ORDER_FIELDS, row)) for row in weather["orders"]}
        self.assertEqual(set(orders), {"cancelled", "filled", "rejected"}, "the order placed before the window is not in it")
        o1 = orders["cancelled"]
        self.assertTrue(o1["real"])
        self.assertEqual((o1["market"], o1["leg"], o1["limit"], o1["quantity"], o1["post_only"]), (market, "no", 0.9, 10.0, True))
        self.assertEqual(o1["filled"], 4.0, "the dust row is not a fill")
        self.assertEqual(o1["fill_price"], 0.9)
        self.assertEqual(o1["liquidity"], "maker")
        self.assertAlmostEqual(o1["placed"], _epoch(placed.at), places=2)
        self.assertAlmostEqual(o1["first_fill"], _epoch(filled.at), places=2)
        self.assertAlmostEqual(o1["end"] - o1["placed"], 900.0, places=1)
        self.assertAlmostEqual(o1["settled"], _epoch(settled.at), places=2)
        o2 = orders["filled"]
        self.assertEqual((o2["real"], o2["post_only"], o2["filled"], o2["liquidity"]), (False, False, 5.0, "taker"))
        self.assertIsNone(o2["settled"])
        self.assertEqual(weather["settles"]["kalshi"]["n"], 1)
        self.assertEqual(weather["settles"]["kalshi"]["markets"], 1)
        self.assertAlmostEqual(weather["settles"]["kalshi"]["pnl"], 0.4)
        self.assertEqual(weather["wakes"]["kalshi"], {"n": 1, "offered_median": 12, "offered_max": 12, "intents": 1})
        self.assertEqual(weather["wakes"]["kalshi-shadow"]["offered_median"], 30)
        self.assertEqual(weather["agents_on_board"], [["mullins-1", "probe", "10"]])
        self.assertEqual(weather["edge_per_dollar"], 0.0078)
        quiet = out["families"]["sports-quiet"]
        self.assertEqual((quiet["orders"], quiet["settles"], quiet["wakes"]), ([], {}, {}), "a positive family with no order is kept, empty")

        named = self.run_snippet(since, board=self.BOARD, extra="crypto-15m-lab-x")
        self.assertEqual(len(named["families"]["crypto-15m-lab-x"]["orders"]), 1, "a family named on the command line is read too")
        every = self.run_snippet(since, board=self.BOARD, extra="*")
        self.assertEqual(set(every["families"]), {"weather-favorites", "sports-quiet", "crypto-15m-lab-x"})

        # And the local half reads it: a family with no orders says so and adds nothing to the totals.
        result = kc.run(out, None)
        rows = {r["family"]: r for r in result["families"]}
        self.assertIn("no order by a member", rows["sports-quiet"]["notes"][0])
        self.assertEqual(result["totals"]["proven"]["1x"]["usd_per_day"], 0.0)
        self.assertEqual(result["position_share"], 0.2)
        self.assertIn("## weather-favorites", kc.render(result))


def _print(at, yes, count, taker="yes", block=False):
    return {"created_time": at, "yes_price_dollars": f"{yes:.4f}", "no_price_dollars": f"{1 - yes:.4f}", "count_fp": f"{count:.2f}",
            "taker_side": taker, "is_block_trade": block, "ticker": "T"}


class TheFillCurve(unittest.TestCase):
    T0 = "2026-09-25T00:00:00Z"

    def at(self, minutes):
        return f"2026-09-25T{minutes // 60:02d}:{minutes % 60:02d}:00Z"

    def test_prints_at_or_through_a_no_bid_whichever_side_took(self):
        start = _epoch(self.T0)
        presence = kc.presences([{"market": "T", "leg": "no", "limit": 0.90, "quantity": 10, "post_only": True, "status": "cancelled",
                                  "placed": start, "end": start + 3600, "filled": 0.0, "real": True}], now=start + 7200)[("T", "no")]
        prints = kc.prints_of([
            _print(self.at(5), 0.10, 3, taker="yes"),    # a YES buyer at 0.10 = NO at 0.90: AT the bid (the queue shares it)
            _print(self.at(6), 0.12, 2, taker="yes"),    # NO at 0.88: through the bid, from the side that hits it
            _print(self.at(7), 0.11, 5, taker="no"),     # a NO buyer at 0.89: a seller under the bid would have crossed it
            _print(self.at(8), 0.09, 7, taker="yes"),    # NO at 0.91: above the bid, not ours
            _print(self.at(9), 0.15, 50, block=True),    # a block trade is not the book's
            _print(self.at(90), 0.20, 11, taker="yes"),  # after the bid was gone
        ])
        self.assertEqual(len(prints), 5, "the block trade is left out")
        flow = kc.market_flow(presence, prints, "no", extend_to=None)
        self.assertEqual(flow, {"estimate": 10.0, "at_or_through": 10.0, "through": 7.0, "floor": 7.0})
        extended = kc.market_flow(presence, prints, "no", extend_to=start + 7200)
        self.assertEqual(extended["estimate"], 21.0, "a filled market's presence goes on at its last price")
        self.assertEqual(extended["floor"], 7.0, "the floor reads the observed windows only")
        yes_bid = dict(presence, windows=[(start, start + 3600, 0.12)], last_price=0.12)
        self.assertEqual(kc.market_flow(yes_bid, prints, "yes", extend_to=None)["estimate"], 17.0,
                         "a YES bid at 0.12: every print at YES 0.12 or under in its hour (3 + 2 + 5 + 7)")

    def test_a_real_fill_is_a_floor_under_the_flow(self):
        start = _epoch(self.T0)
        presence = kc.presences([{"market": "T", "leg": "yes", "limit": 0.40, "quantity": 5, "post_only": True, "status": "filled",
                                  "placed": start, "end": start + 60, "filled": 5.0, "first_fill": start + 60, "real": True}],
                                now=start + 600)[("T", "yes")]
        flow = kc.market_flow(presence, [], "yes", extend_to=None)
        self.assertEqual(flow["floor"], 5.0, "what the real book filled happened, prints or none")

    def test_fractions_rates_and_halving(self):
        self.assertEqual(kc.fraction(3, 10), 0.3)
        self.assertEqual(kc.fraction(30, 10), 1.0)
        self.assertEqual(kc.fraction(-1, 10), 0.0)
        caps = [8.0, 1.0, 0.5, 0.0]
        self.assertAlmostEqual(kc.curve_rate(caps, 1), (1 + 1 + 0.5 + 0) / 4)
        self.assertAlmostEqual(kc.curve_rate(caps, 2), (1 + 0.5 + 0.25 + 0) / 4)
        self.assertAlmostEqual(kc.curve_rate(caps, 8), (1 + 0.125 + 0.0625 + 0) / 4)
        self.assertIsNone(kc.curve_rate([], 1))
        # 1x rate 0.625; half is 0.3125; (min(8/k,1) + 1/k + 0.5/k) / 4 = 0.3125 at k = 1.5 / 0.25 = 6 (8/k >= 1 there).
        self.assertAlmostEqual(kc.halving(lambda k: kc.curve_rate(caps, k)), 6.0, delta=0.01)
        self.assertIsNone(kc.halving(lambda k: kc.curve_rate([1000.0], k)), "flow for 1000x never halves inside 256x")
        self.assertIsNone(kc.halving(lambda k: kc.curve_rate([0.0], k)), "no 1x fill, nothing to halve")
        self.assertAlmostEqual(kc.halving(lambda k: kc.curve_rate([1.0], k)), 2.0, delta=0.01,
                               msg="flow for exactly one order halves just past 2x")

    def test_recorded_prints_parse_and_flow_by_leg(self):
        data = json.loads(FIXTURE.read_text())
        raw = data["trades"]["trades"]
        prints = kc.prints_of(raw)
        self.assertEqual(len(prints), sum(1 for t in raw if not t.get("is_block_trade")))
        self.assertEqual([p[0] for p in prints], sorted(p[0] for p in prints), "oldest first")
        for _, yes, no, _ in prints:
            self.assertAlmostEqual(yes + no, 1.0, places=6)
        self.assertEqual(sorted((round(yes, 4), count) for _, yes, _, count in prints),
                         sorted((float(t["yes_price_dollars"]), float(t["count_fp"])) for t in raw if not t.get("is_block_trade")))
        start, end = prints[0][0], prints[-1][0]
        bid = float(data["trades_bid_no"])
        presence = kc.presences([{"market": data["trades_ticker"], "leg": "no", "limit": bid, "quantity": 10, "post_only": True,
                                  "status": "cancelled", "placed": start, "end": end, "filled": 0.0, "real": False}],
                                now=end)[(data["trades_ticker"], "no")]
        flow = kc.market_flow(presence, prints, "no", extend_to=None)
        by_hand = sum(float(t["count_fp"]) for t in raw if not t.get("is_block_trade") and float(t["no_price_dollars"]) <= bid + 1e-9)
        through = sum(float(t["count_fp"]) for t in raw if not t.get("is_block_trade") and float(t["no_price_dollars"]) < bid - 1e-9)
        self.assertAlmostEqual(flow["estimate"], by_hand)
        self.assertAlmostEqual(flow["floor"], through)
        self.assertGreater(by_hand, through, "the recorded window has prints at the bid itself")


class TheTakerSide(unittest.TestCase):
    def setUp(self):
        from ltcm.data.kalshi import KalshiMarketData

        self.data = json.loads(FIXTURE.read_text())
        self.books = {row["ticker"]: KalshiMarketData.parse_book(row["ticker"], row) for row in self.data["orderbooks"]["orderbooks"]}

    def test_depth_at_the_limit_from_the_other_legs_bids(self):
        ticker, book = next(iter(self.books.items()))
        raw = next(row for row in self.data["orderbooks"]["orderbooks"] if row["ticker"] == ticker)["orderbook_fp"]
        yes_bids = [(float(p), float(c)) for p, c in raw["yes_dollars"]]
        no_bids = [(float(p), float(c)) for p, c in raw["no_dollars"]]
        ask_no, depth = kc.book_depth(book, "no", 1.0)
        self.assertAlmostEqual(ask_no, 1 - max(p for p, _ in yes_bids), places=4, msg="the NO ask is the best YES bid's complement")
        self.assertAlmostEqual(depth, sum(c for _, c in yes_bids), msg="at a limit of $1 every YES bid is offered NO")
        _, at_touch = kc.book_depth(book, "no", ask_no)
        self.assertAlmostEqual(at_touch, sum(c for p, c in yes_bids if 1 - p <= ask_no + 1e-9))
        ask_yes, _ = kc.book_depth(book, "yes", 1.0)
        _, two_cents = kc.book_depth(book, "yes", ask_yes + 0.02)
        self.assertAlmostEqual(two_cents, sum(c for p, c in no_bids if 1 - p <= ask_yes + 0.02 + 1e-9))

    def test_the_curve_from_books_in_band_now(self):
        band = {"leg": "no", "series": [self.data["series"]], "lo": 0.01, "hi": 0.99, "allowance": 0.0}
        markets = [{"ticker": t, "ask": 0.5, "close": 0} for t in self.books]
        rows = kc.taker_capacities(self.books, markets, band, size_usd=6.0)
        self.assertEqual(len(rows), len(self.books))
        for r in rows:
            _, depth = kc.book_depth(self.books[r["ticker"]], "no", r["ask"])
            self.assertEqual(r["limit"], r["ask"], "no allowance: the limit is the ask")
            self.assertAlmostEqual(r["capacity"], depth / (6.0 / r["ask"]))
        capped = kc.taker_capacities(self.books, markets, dict(band, hi=0.01), size_usd=6.0)
        self.assertTrue(all(r["limit"] == r["ask"] for r in capped), "a band under the ask never bids under the ask")

    def test_markets_in_band_from_a_recorded_listing(self):
        from ltcm.data.kalshi import KalshiMarketData

        parsed = [KalshiMarketData.parse_market(m) for m in self.data["markets"]["markets"]]

        class Listing:
            requests = 0
            truncated: list = []

            def open_markets(self, series):
                return parsed

        asks = sorted(float(m["no_ask"]) for m in parsed if m.get("no_ask") is not None)
        lo, hi = asks[0], asks[len(asks) // 2]
        band = {"leg": "no", "series": [self.data["series"]], "lo": lo, "hi": hi, "allowance": 0.0}
        now = min(_epoch(m["close_time"]) for m in parsed) - 3600
        chosen = kc.taker_markets(Listing(), band, now=now, limit=100)
        self.assertEqual(len(chosen), sum(1 for m in parsed if m.get("no_ask") is not None and lo <= float(m["no_ask"]) <= hi))
        self.assertEqual([c["close"] for c in chosen], sorted(c["close"] for c in chosen), "soonest to resolve first")


class ThePublicReads(unittest.TestCase):
    """`Public` pages Kalshi's prints by cursor, waits out a 429, and keeps a closed window's prints on disk."""

    class Transport:
        def __init__(self, answers):
            self.answers = list(answers)
            self.urls = []

        def get(self, url, headers=None, timeout=None):
            self.urls.append(url)
            status, body = self.answers.pop(0)
            return status, {}, json.dumps(body).encode()

    def test_paging_retry_and_the_disk_cache(self):
        from ltcm.data.kalshi import KalshiMarketData

        one, two = _print("2026-09-25T00:01:00Z", 0.1, 1), _print("2026-09-25T00:00:00Z", 0.1, 2)
        transport = self.Transport([(429, {}), (200, {"trades": [one], "cursor": "c1"}), (200, {"trades": [two], "cursor": ""})])
        waits = []
        with tempfile.TemporaryDirectory() as cache:
            public = kc.Public(KalshiMarketData(transport), cache_dir=cache, clock=lambda: 2e9, sleep=waits.append)
            rows = public.trades("KXHIGHNY-26SEP25-T70", 1.7e9, 1.7e9 + 3600)
            self.assertEqual([r["count_fp"] for r in rows], ["1.00", "2.00"], "both pages, newest first")
            self.assertEqual((public.requests, waits), (3, [2.0]), "the 429 was waited out and asked again")
            self.assertIn("cursor=c1", transport.urls[-1])
            self.assertIn("min_ts=1700000000", transport.urls[0])
            self.assertIs(public.trades("KXHIGHNY-26SEP25-T70", 1.7e9, 1.7e9 + 3600), rows, "read once a run")
            again = kc.Public(KalshiMarketData(self.Transport([])), cache_dir=cache, clock=lambda: 2e9)
            self.assertEqual(again.trades("KXHIGHNY-26SEP25-T70", 1.7e9, 1.7e9 + 3600), rows, "a closed window comes from disk")
            self.assertEqual(again.requests, 0)


class FakePublic:
    """Prints by ticker, listings by series and books by ticker, as `Public` returns them."""

    def __init__(self, trades=None, listings=None, books=None):
        self.trades_by = trades or {}
        self.listings = listings or {}
        self.book_rows = books or {}
        self.requests = 0
        self.truncated: list = []
        self.asked: list = []

    def trades(self, ticker, min_ts, max_ts):
        self.asked.append((ticker, min_ts, max_ts))
        return [t for t in self.trades_by.get(ticker, []) if min_ts <= _epoch(t["created_time"]) <= max_ts]

    def open_markets(self, series):
        return self.listings.get(series, [])

    def books(self, tickers):
        return {t: self.book_rows[t] for t in tickers if t in self.book_rows}


class TheFamilyCurveAndTotals(unittest.TestCase):
    def family(self):
        start = _epoch("2026-09-24T00:00:00Z")
        orders = []
        # Four weather markets, NO bids at 0.90 for an hour; two filled after ten minutes on the real book.
        for i in range(4):
            placed = start + i * 6 * 3600
            filled = i < 2
            orders.append([True, f"KXHIGHNY-M{i}", "no", 0.90, 0.90, 10.0, True, placed, placed + (600 if filled else 3600),
                           "filled" if filled else "cancelled", 10.0 if filled else 0.0, placed + 600 if filled else None,
                           "maker" if filled else None, 0.90 if filled else None, "mullins-1",
                           placed + 0.5 * 86400 if filled else None])
        orders.append([False, "KXHIGHNY-M9", "no", 0.90, 0.90, 10.0, True, start, start + 60, "rejected", 0.0, None, None, None, "mullins-2",
                       None])
        return start, {"state": "proven", "proven": True, "n": 30, "mean_log": 0.1, "edge_per_dollar": 0.05, "stake_usd": "10",
                       "capacity": {"size_usd": 2.7}, "members_living": 2, "orders": orders,
                       "settles": {"kalshi": {"n": 2, "markets": 2, "pnl": 1.0, "cost": 18.0}}, "wakes": {}}

    def test_the_curve_halving_and_envelope_of_one_family(self):
        start, family = self.family()
        trades = {}
        for i in range(4):
            placed = start + i * 6 * 3600
            at = datetime.fromtimestamp(placed + 300, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            # Market i prints 3 x (i + 1) contracts at the bid (YES 0.10) five minutes in; 3 contracts is one $2.70 order.
            trades[f"KXHIGHNY-M{i}"] = [_print(at + "Z", 0.10, 3.0 * (i + 1))]
        public = FakePublic(trades=trades)
        now = start + 4 * 86400
        row = kc.family_capacity("weather-favorites", family, public, since=start, now=now, share=0.2)
        self.assertEqual(row["stats"]["pooled"]["orders"], 4)
        self.assertEqual(row["stats"]["pooled"]["rejected"], 1)
        self.assertEqual(row["stats"]["real"]["markets"], 4)
        self.assertAlmostEqual(row["stats"]["real"]["fill_fraction_mean"], 0.5)
        self.assertAlmostEqual(row["stats"]["real"]["hold_days_median"], 0.5 - 600 / 86400, places=3)
        self.assertEqual(row["size_usd"], 2.7)
        # 3 contracts of 0.90 = $2.70: market i's capacity is i + 1; the curve is mean(min((i + 1) / k, 1)).
        self.assertAlmostEqual(row["curve"]["1x"]["fill_rate"], 1.0)
        self.assertAlmostEqual(row["curve"]["2x"]["fill_rate"], (0.5 + 1 + 1 + 1) / 4)
        self.assertAlmostEqual(row["curve"]["4x"]["fill_rate"], (0.25 + 0.5 + 0.75 + 1) / 4)
        self.assertAlmostEqual(row["curve"]["8x"]["fill_rate"], (1 + 2 + 3 + 4) / 8 / 4)
        # The halving: 10 / 4k = 0.5 at k = 5.
        self.assertAlmostEqual(row["halves_at"], 5.0, delta=0.01)
        mpd = row["markets_per_day"]
        self.assertAlmostEqual(row["curve"]["4x"]["usd_per_day"], round(mpd * 0.625 * 4 * 2.7 * 0.05, 2))
        self.assertEqual(row["curve"]["4x"]["stake_usd"], 54.0, "4 x $2.70 is 20% of $54")
        open_positions = mpd * 0.625 * row["stats"]["pooled"]["hold_days_median"]
        self.assertAlmostEqual(row["curve"]["4x"]["open_positions"], round(open_positions, 2))
        self.assertEqual(row["curve"]["4x"]["members"], max(1, math.ceil(open_positions * 0.2)))
        self.assertEqual(row["curve"]["4x"]["envelope_usd"], round(54.0 * row["curve"]["4x"]["members"], 2))
        self.assertAlmostEqual(row["curve"]["1x"]["fill_floor"], 0.5, msg="the floor: the two real fills of 10 (> 3 contracts), none else")
        # Two unfilled markets are too few to measure patience by: the median life of the four maker orders (600, 600,
        # 3600, 3600 s) is 35 minutes, and each filled market is watched that long after it was bid.
        self.assertEqual(row["patience_minutes"], 35.0)
        filled_markets = [a for a in public.asked if a[0] in ("KXHIGHNY-M0", "KXHIGHNY-M1")]
        self.assertEqual([round(a[2] - a[1]) for a in filled_markets], [2102, 2102], "a filled market is watched for the family's patience")
        # At their own 10 contracts the prints (3, 6, 9, 12) would have filled 0.3, 0.6, 0.9 and 1.0 of the real bids.
        self.assertEqual(row["real_check"], {"markets": 4, "filled": 0.5, "at_or_through": 0.7, "through": 0.0})

    def test_a_family_with_no_orders_and_the_totals(self):
        start, family = self.family()
        empty = {"state": "unproven", "proven": False, "n": 3, "mean_log": 0.4, "edge_per_dollar": 0.4, "orders": [], "settles": {},
                 "capacity": {"size_usd": 2.0}, "stake_usd": "10"}
        public = FakePublic()
        rows = [kc.family_capacity("weather-favorites", family, public, since=start, now=start + 4 * 86400, share=0.2),
                kc.family_capacity("sports-new", empty, public, since=start, now=start + 4 * 86400, share=0.2)]
        self.assertEqual(rows[1]["curve"], {})
        self.assertTrue(rows[1]["notes"][0].startswith("no order by a member"))
        self.assertEqual(rows[0]["curve"]["1x"]["fill_rate"], 0.0, "no print at all: the prints say nothing filled")
        self.assertEqual(rows[0]["curve"]["1x"]["fill_floor"], 0.5, "the real fills still happened")
        t = kc.totals(rows, {"committed_usd": "109.23", "capital_usd": "546.83"})
        self.assertEqual((t["proven"]["families"], t["positive"]["families"]), (1, 2))
        self.assertEqual(t["proven"]["1x"]["usd_per_day_floor"], rows[0]["curve"]["1x"]["usd_per_day_floor"])
        self.assertEqual((t["committed_usd"], t["capital_usd"]), (109.23, 546.83))
        text = kc.render({"families": rows, "totals": t, "envelope": {"committed_usd": "109.23", "capital_usd": "546.83"}})
        self.assertIn("TOTAL proven (1 families)", text)
        self.assertIn("note: no order by a member", text)

    def test_the_taker_side_of_a_family_and_its_blend(self):
        from ltcm.data.kalshi import KalshiMarketData

        start = _epoch("2026-09-24T00:00:00Z")
        orders = [[True, "KXMLBTOTAL-26SEP24NYYBOS-9", "no", 0.60, 0.60, 10.0, False, start, start + 1, "filled", 6.0, start + 1, "taker",
                   0.60, "meriwether-1", None],
                  [True, "KXMLBTOTAL-26SEP24NYYBOS-9", "no", 0.60, 0.60, 10.0, True, start, start + 3600, "cancelled", 0.0, None, None,
                   None, "meriwether-1", None]]
        family = {"state": "proven", "proven": True, "n": 30, "mean_log": 0.2, "edge_per_dollar": 0.2, "stake_usd": "30",
                  "capacity": {"size_usd": 6.0}, "orders": orders, "settles": {}}
        book = KalshiMarketData.parse_book("X", {"orderbook_fp": {"yes_dollars": [["0.38", "5"], ["0.40", "10"]], "no_dollars": [["0.55", "3"]]}})
        listing = [{"ticker": "X", "no_ask": 0.60, "close_time": "2026-09-30T00:00:00Z"}]
        public = FakePublic(listings={"KXMLBTOTAL": listing}, books={"X": book})
        row = kc.family_capacity("sports-central-run-under", family, public, since=start, now=start + 86400, share=0.2)
        self.assertEqual(row["stats"]["real"]["taker_partial_share"], 1.0, "its one taker fill was partial")
        self.assertEqual(row["taker_band"]["series"], ["KXMLBTOTAL"])
        # NO ask 0.60 offers 10 contracts; one $6 order is 10 contracts: capacity 1.0; at 2x half of it.
        self.assertEqual(row["taker_books"][0]["depth"], 10.0)
        self.assertAlmostEqual(row["curve"]["2x"]["taker_fill"], 0.5)
        self.assertAlmostEqual(row["curve"]["1x"]["maker_fill"], 0.0)
        self.assertAlmostEqual(row["curve"]["1x"]["fill_rate"], 0.5, msg="one maker market, one taker market: equal weights")

        # No market inside the band now (a fifteen-minute series has one open at a time): its nearest is read at its touch.
        away = KalshiMarketData.parse_book("Y", {"orderbook_fp": {"yes_dollars": [["0.97", "40"]], "no_dollars": [["0.01", "9"]]}})
        public = FakePublic(listings={"KXMLBTOTAL": [{"ticker": "Y", "no_ask": 0.03, "close_time": "2026-09-30T00:00:00Z"}]},
                            books={"Y": away})
        row = kc.family_capacity("sports-central-run-under", family, public, since=start, now=start + 86400, share=0.2)
        self.assertEqual([r["ticker"] for r in row["taker_books"]], ["Y"])
        self.assertEqual(row["taker_books"][0]["limit"], 0.03, "at its own touch, not the band's price")
        self.assertAlmostEqual(row["curve"]["1x"]["taker_fill"], 40 / (6.0 / 0.03))
        self.assertTrue(any("nearest it read at their touch" in n for n in row["notes"]))


if __name__ == "__main__":
    unittest.main()
