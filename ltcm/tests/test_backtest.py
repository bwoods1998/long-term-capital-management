"""Backtests: history as of a moment, a conservative book, and the report contract. No network."""

from __future__ import annotations

import contextlib
import io
import json
import math
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from ltcm.backtest import (
    KIT_CALLS,
    RESULT_PREFIX,
    BacktestKit,
    CodeRefused,
    DataSet,
    Simulator,
    bootstrap_ci,
    check_code,
    iso,
    kalshi_plan,
    kalshi_taker_fee,
    main,
    max_drawdown,
    parse_time,
    run_backtest,
    sample_markets,
    split_report,
)
from ltcm.history import DiskCache, History, HistoryTimeout

T0 = parse_time("2026-09-10T00:00:00Z")
HOUR = 3600
MINUTE = 60


def candle(ts, bid, ask, *, bid_high=None, ask_low=None, volume=0.0, price=None, interest=0.0):
    return {
        "ts": int(ts),
        "yes_bid_open": bid, "yes_bid_high": bid if bid_high is None else bid_high, "yes_bid_low": bid, "yes_bid_close": bid,
        "yes_ask_open": ask, "yes_ask_high": ask, "yes_ask_low": ask if ask_low is None else ask_low, "yes_ask_close": ask,
        "volume": volume, "open_interest": interest, "price_close": price,
    }


def market_row(ticker, open_ts, close_ts, *, result="no", volume=5000, title="A market", **extra):
    return {
        "ticker": ticker,
        "event_ticker": "-".join(ticker.split("-")[:2]),
        "title": title,
        "yes_sub_title": extra.pop("yes_sub_title", title),
        "open_time": iso(open_ts),
        "close_time": iso(close_ts),
        "result": result,
        "volume": volume,
        **extra,
    }


class FakeHistory:
    """Synthetic markets and candles; records what the engine asked for."""

    def __init__(self, markets=(), candles=None, coinbase=None):
        self.markets = list(markets)
        self.candles = dict(candles or {})  # (ticker, period minutes) -> [candle]
        self.coinbase = dict(coinbase or {})  # (product, granularity) -> [candle]
        self.calls = []
        self.requests = 0

    def kalshi_settled(self, series=None, *, start_ts, end_ts, max_pages=20, min_volume=0):
        self.calls.append(("settled", series, start_ts, end_ts))
        out = []
        for row in self.markets:
            close = parse_time(row["close_time"])
            if not start_ts <= close <= end_ts:
                continue
            if series and not row["ticker"].startswith(series + "-"):
                continue
            if float(row.get("volume") or 0) < float(min_volume):
                continue
            out.append(dict(row))
        return out

    def kalshi_candles(self, series, ticker, *, start_ts, end_ts, period_minutes=60):
        self.calls.append(("candles", ticker, start_ts, end_ts, period_minutes))
        return [dict(c) for c in self.candles.get((ticker, period_minutes), []) if start_ts <= c["ts"] <= end_ts + period_minutes * 60]

    def coinbase_candles(self, product, *, start_ts, end_ts, granularity="FIVE_MINUTE"):
        self.calls.append(("coinbase", product, start_ts, end_ts, granularity))
        return [dict(c) for c in self.coinbase.get((product, granularity), []) if start_ts <= c["ts"] <= end_ts]


def one_hour_market(ticker="KXTEST-26SEP10-T1", open_ts=T0 + 10 * HOUR, *, result="no", minute_candles=None, **extra):
    close = open_ts + HOUR
    row = market_row(ticker, open_ts, close, result=result, **extra)
    return row, {(ticker, 1): list(minute_candles or [])}


def dataset(history, start=T0, end=T0 + 24 * HOUR, series=("KXTEST",)):
    notes = []
    data = DataSet(history, start, end, say=lambda text: None, notes=notes)
    data.load_kalshi(series=list(series), board=False, max_markets=3000, max_pages=20)
    return data


def simulator(data, strategy="tester"):
    return Simulator(data, strategy=strategy, learning_usd=10, half_spread=0.0001, maker_fee=0.0025, taker_fee=0.006)


def buy(ticker, right, price, quantity=5, **extra):
    return {
        "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": right},
        "side": "buy",
        "quantity": str(quantity),
        "order_type": "limit",
        "limit_price": f"{price:.2f}",
        "rationale": "test",
        **extra,
    }


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.open = T0 + 10 * HOUR
        row, candles = one_hour_market(open_ts=self.open, minute_candles=[
            candle(self.open + 1 * MINUTE, 0.40, 0.45, volume=10),
            candle(self.open + 2 * MINUTE, 0.50, 0.55, volume=7),
        ])
        self.history = FakeHistory([row], candles)
        self.data = dataset(self.history)
        self.sim = simulator(self.data)

    def kit(self, t):
        return BacktestKit(self.data, self.sim, t, products=None, half_spread=0.0001)

    def test_no_market_is_visible_before_it_opens_or_after_it_closes(self):
        close = self.open + HOUR
        for t, visible in ((self.open - 1, False), (self.open, True), (close - 1, True), (close, False), (close + HOUR, False)):
            kit = self.kit(t)
            self.assertEqual(bool(kit.kalshi_series("KXTEST")), visible, iso(t))
            self.assertEqual(kit.kalshi_market("KXTEST-26SEP10-T1") is not None, visible, iso(t))
            self.assertEqual(bool(kit.kalshi_markets(max_close_hours=48)), visible, iso(t))

    def test_prices_never_come_from_a_candle_that_ended_after_now(self):
        before = self.kit(self.open + 30).kalshi_market("KXTEST-26SEP10-T1")
        self.assertIsNone(before["yes_bid"], "no candle had ended: no prices")
        self.assertIsNone(before["yes_ask"])
        mid = self.kit(self.open + 90).kalshi_market("KXTEST-26SEP10-T1")
        self.assertEqual(str(mid["yes_bid"]), "0.4000")
        self.assertEqual(str(mid["yes_ask"]), "0.4500")
        self.assertEqual(str(mid["no_bid"]), "0.5500")
        self.assertEqual(str(mid["no_ask"]), "0.6000")
        at_end = self.kit(self.open + 120).kalshi_market("KXTEST-26SEP10-T1")
        self.assertEqual(str(at_end["yes_bid"]), "0.5000", "a candle that ended exactly now is known now")
        self.assertEqual(float(at_end["volume_24h"]), 17.0)
        self.assertEqual(at_end["status"], "active")
        self.assertIsNone(at_end["result"], "the settled result never leaks into an open listing")

    def test_kalshi_markets_filters_by_close_horizon(self):
        kit = self.kit(self.open + 120)
        self.assertEqual(kit.kalshi_markets(max_close_hours=0.5), [])
        self.assertEqual(len(kit.kalshi_markets(max_close_hours=1)), 1)

    def test_kalshi_orderbooks_is_the_candle_top_of_book_in_the_floor_kits_shape(self):
        self.assertIn("kalshi_orderbooks", KIT_CALLS)
        books = self.kit(self.open + 90).strategy_kit().kalshi_orderbooks(["kxtest-26sep10-t1", "KXTEST-26SEP10-T1", "KXNOPE-26SEP10-A"])
        self.assertEqual(set(books), {"KXTEST-26SEP10-T1"}, "one book per open market; an unknown ticker has none")
        book = books["KXTEST-26SEP10-T1"]
        self.assertEqual(
            {key: str(book[key]) for key in ("yes_bid", "yes_ask", "no_bid", "no_ask")},
            {"yes_bid": "0.4000", "yes_ask": "0.4500", "no_bid": "0.5500", "no_ask": "0.6000"},
            "the same candle the listing row shows",
        )
        self.assertEqual((book["yes"], book["no"]), ([(Decimal("0.4000"), None)], [(Decimal("0.5500"), None)]), "one level a side, no depth")
        self.assertEqual(self.kit(self.open + 30).kalshi_orderbooks(["KXTEST-26SEP10-T1"]), {}, "no candle had ended: no book")
        self.assertEqual(self.kit(self.open + HOUR).kalshi_orderbooks(["KXTEST-26SEP10-T1"]), {}, "closed: no book")
        many = [f"KXNOPE-26SEP10-{n}" for n in range(400)] + ["KXTEST-26SEP10-T1"]
        self.assertEqual(self.kit(self.open + 90).kalshi_orderbooks(many), {}, "300 tickers a run, as on the floor")

    def test_an_early_close_is_listed_at_its_scheduled_close_and_trades_until_the_real_one(self):
        open_ts = T0 + 2 * HOUR
        actual = T0 + 20 * HOUR + 29 * MINUTE + 49
        latest = T0 + 3 * 86400
        ticker = "KXGAME-26SEP10-A"
        row = market_row(ticker, open_ts, actual, result="yes", can_close_early=True, latest_expiration_time=iso(latest))
        history = FakeHistory([row], {(ticker, 60): [candle(open_ts + h * HOUR, 0.05, 0.08) for h in range(1, 16)]})
        data = dataset(history, start=T0, end=T0 + 30 * HOUR, series=("KXGAME",))
        sim = simulator(data)
        kit = BacktestKit(data, sim, T0 + 10 * HOUR, products=None, half_spread=0.0)
        self.assertEqual(kit.kalshi_market(ticker)["close_time"], iso(latest), "the listing never shows when the game ends")
        self.assertEqual(kit.kalshi_markets(max_close_hours=36), [], "a close three days out is outside 36 hours")
        self.assertEqual(len(kit.kalshi_series("KXGAME")), 1)
        self.assertIsNone(BacktestKit(data, sim, actual, products=None, half_spread=0.0).kalshi_market(ticker))
        self.assertEqual(sim.submit(buy(ticker, "no", 0.95, 10), T0 + 10 * HOUR), "filled", "it trades while it is open")
        sim.advance(actual)
        self.assertEqual(sim.closed[0]["ts"], actual, "and settles when trading really stopped")
        self.assertLess(sim.closed[0]["pnl"], 0)
        on_time = market_row("KXBTCD-26SEP1017-T1", open_ts, T0 + 21 * HOUR, can_close_early=True, latest_expiration_time=iso(latest))
        data = dataset(FakeHistory([on_time]), start=T0, end=T0 + 30 * HOUR, series=("KXBTCD",))
        view = BacktestKit(data, simulator(data), T0 + 10 * HOUR, products=None, half_spread=0.0).kalshi_market("KXBTCD-26SEP1017-T1")
        self.assertEqual(view["close_time"], iso(T0 + 21 * HOUR), "a close on the whole minute is the scheduled one")

    def test_volume_24h_counts_only_the_last_day(self):
        open_ts = T0 + 2 * HOUR
        close = open_ts + 40 * HOUR
        row = market_row("KXLONG-26SEP11-A", open_ts, close)
        hourly = [candle(open_ts + (i + 1) * HOUR, 0.2, 0.3, volume=1.0) for i in range(30)]
        history = FakeHistory([row], {("KXLONG-26SEP11-A", 60): hourly})
        data = dataset(history, start=T0, end=T0 + 48 * HOUR, series=("KXLONG",))
        kit = BacktestKit(data, simulator(data), open_ts + 30 * HOUR, products=None, half_spread=0.0)
        view = kit.kalshi_market("KXLONG-26SEP11-A")
        self.assertEqual(float(view["volume_24h"]), 24.0)
        self.assertEqual(float(view["volume"]), 30.0)


class FillTests(unittest.TestCase):
    def setUp(self):
        self.open = T0 + 10 * HOUR
        self.ticker = "KXTEST-26SEP10-T1"

    def build(self, minute_candles, result="no"):
        row, candles = one_hour_market(self.ticker, self.open, result=result, minute_candles=minute_candles)
        self.data = dataset(FakeHistory([row], candles))
        self.sim = simulator(self.data)
        return self.sim

    def test_taker_buy_fills_at_the_ask_and_pays_the_fee(self):
        sim = self.build([candle(self.open + MINUTE, 0.52, 0.55)])
        t = self.open + 5 * MINUTE
        self.assertEqual(sim.submit(buy(self.ticker, "yes", 0.60, 5), t), "filled")
        fill = sim.fills[-1]
        self.assertAlmostEqual(fill["price"], 0.55)
        # 0.07 x 5 x 0.55 x 0.45 = 0.086625, charged to the $0.0001 for the whole fill.
        self.assertAlmostEqual(fill["fee"], kalshi_taker_fee(0.55, 5))
        self.assertEqual(kalshi_taker_fee(0.55, 5), 0.0867)
        self.assertEqual(kalshi_taker_fee(0.55), 0.0174)
        self.assertFalse(fill["maker"])
        self.assertEqual(sim.submit(buy(self.ticker, "no", 0.50, 3), t), "filled", "NO ask = 1 - yes_bid = 0.48")
        self.assertAlmostEqual(sim.fills[-1]["price"], 0.48)
        context = sim.context(t)
        legs = {(p["market_id"], p["right"]): p for p in context["positions"]}
        self.assertEqual(legs[(self.ticker, "yes")]["quantity"], "5")
        self.assertEqual(legs[(self.ticker, "yes")]["average_cost"], "0.55")

    def test_a_bid_under_the_ask_rests_and_fills_only_on_a_later_candle_trading_strictly_through(self):
        sub = self.open + 10 * MINUTE
        sim = self.build([
            candle(self.open + 10 * MINUTE, 0.40, 0.50, ask_low=0.30),  # ended at submission: not later
            candle(self.open + 11 * MINUTE, 0.40, 0.50, ask_low=0.45),  # touches, does not trade through
            candle(self.open + 12 * MINUTE, 0.40, 0.50, ask_low=0.44),  # through
        ])
        status = sim.submit(buy(self.ticker, "yes", 0.45, 4), sub)
        self.assertTrue(status.startswith("resting:"), status)
        sim.advance(self.open + 11 * MINUTE)
        self.assertEqual(sim.fills, [], "a touch is not a fill")
        self.assertEqual(len(sim.context(self.open + 11 * MINUTE)["open_orders"]), 1)
        sim.advance(self.open + 12 * MINUTE)
        self.assertEqual(len(sim.fills), 1)
        fill = sim.fills[0]
        self.assertAlmostEqual(fill["price"], 0.45, msg="a maker fills at its own limit")
        self.assertEqual(fill["fee"], 0.0)
        self.assertTrue(fill["maker"])
        self.assertEqual(fill["ts"], self.open + 12 * MINUTE)

    def test_a_no_bid_fills_when_the_yes_bid_trades_strictly_above_its_complement(self):
        sub = self.open + 5 * MINUTE
        sim = self.build([
            candle(self.open + 5 * MINUTE, 0.40, 0.55),
            candle(self.open + 6 * MINUTE, 0.45, 0.55, bid_high=0.50),
            candle(self.open + 7 * MINUTE, 0.45, 0.55, bid_high=0.51),
        ])
        self.assertTrue(sim.submit(buy(self.ticker, "no", 0.50, 2), sub).startswith("resting:"))
        sim.advance(self.open + 6 * MINUTE)
        self.assertEqual(sim.fills, [])
        sim.advance(self.open + 7 * MINUTE)
        self.assertEqual(len(sim.fills), 1)
        self.assertAlmostEqual(sim.fills[0]["price"], 0.50)

    def test_the_touch_model_fills_on_a_touch_or_a_print_where_the_conservative_one_does_not(self):
        minutes = [
            candle(self.open + 5 * MINUTE, 0.40, 0.55),
            candle(self.open + 6 * MINUTE, 0.45, 0.55, bid_high=0.50),  # touches 1 - q
        ]
        for model, expected in (("conservative", 0), ("touch", 1)):
            sim = self.build(minutes)
            sim.fill_model = model
            sim.submit(buy(self.ticker, "no", 0.50, 2), self.open + 5 * MINUTE)
            sim.advance(self.open + 6 * MINUTE)
            self.assertEqual(len(sim.fills), expected, model)
        printed = [candle(self.open + 5 * MINUTE, 0.40, 0.55), {**candle(self.open + 6 * MINUTE, 0.40, 0.55), "price_low": 0.42}]
        for model, expected in (("conservative", 0), ("touch", 1)):
            sim = self.build(printed)
            sim.fill_model = model
            sim.submit(buy(self.ticker, "yes", 0.42, 2), self.open + 5 * MINUTE)
            sim.advance(self.open + 6 * MINUTE)
            self.assertEqual(len(sim.fills), expected, model)

    def test_an_hourly_candle_that_began_before_the_order_is_judged_on_its_close(self):
        open_ts = T0 + 1 * HOUR
        close = open_ts + 30 * HOUR
        ticker = "KXLONG-26SEP11-A"
        hourly = [
            candle(open_ts + HOUR, 0.10, 0.20),
            candle(open_ts + 2 * HOUR, 0.10, 0.20, ask_low=0.05),  # the low printed before the order
            candle(open_ts + 3 * HOUR, 0.10, 0.12),  # closes through the bid
        ]
        data = dataset(FakeHistory([market_row(ticker, open_ts, close)], {(ticker, 60): hourly}), end=T0 + 48 * HOUR, series=("KXLONG",))
        sim = simulator(data)
        self.assertTrue(sim.submit(buy(ticker, "yes", 0.15, 3), open_ts + HOUR + 30 * MINUTE).startswith("resting:"))
        sim.advance(open_ts + 2 * HOUR)
        self.assertEqual(sim.fills, [], "an extreme from before the order cannot fill it")
        sim.advance(open_ts + 3 * HOUR)
        self.assertEqual(len(sim.fills), 1)

    def test_an_order_resting_on_an_hourly_market_is_judged_on_minute_candles(self):
        open_ts = T0 + 1 * HOUR
        close = open_ts + 30 * HOUR
        ticker = "KXLONG-26SEP11-A"
        sub = open_ts + HOUR + 20 * MINUTE
        hourly = [candle(open_ts + h * HOUR, 0.10, 0.20, ask_low=0.05) for h in range(1, 28)]
        minutes = [
            candle(open_ts + HOUR + 10 * MINUTE, 0.10, 0.20, ask_low=0.05),  # before the order
            candle(open_ts + HOUR + 25 * MINUTE, 0.10, 0.20, ask_low=0.16),  # after, not through
            candle(open_ts + HOUR + 40 * MINUTE, 0.10, 0.20, ask_low=0.14),  # after, through
        ]
        history = FakeHistory([market_row(ticker, open_ts, close)], {(ticker, 60): hourly, (ticker, 1): minutes})
        data = dataset(history, end=T0 + 48 * HOUR, series=("KXLONG",))
        sim = simulator(data)
        self.assertTrue(sim.submit(buy(ticker, "yes", 0.15, 3), sub).startswith("resting:"))
        sim.advance(open_ts + HOUR + 30 * MINUTE)
        self.assertIn(ticker, data.refined)
        self.assertEqual(sim.fills, [], "the minute before the order does not fill it")
        requested = [c for c in history.calls if c[0] == "candles" and c[4] == 1 and c[2] == open_ts + HOUR]
        self.assertTrue(requested, "minute candles are fetched from the hour the order rests in")
        sim.advance(open_ts + HOUR + 45 * MINUTE)
        self.assertEqual(len(sim.fills), 1)
        self.assertEqual(sim.fills[0]["ts"], open_ts + HOUR + 40 * MINUTE)
        view = BacktestKit(data, sim, open_ts + HOUR + 26 * MINUTE, products=None, half_spread=0.0).kalshi_market(ticker)
        self.assertEqual(str(view["yes_ask"]), "0.2000")

    def test_post_only_that_would_cross_is_rejected(self):
        sim = self.build([candle(self.open + MINUTE, 0.40, 0.45)])
        t = self.open + 2 * MINUTE
        status = sim.submit(buy(self.ticker, "yes", 0.45, 2, post_only=True), t)
        self.assertEqual(status, "rejected:post-only order would cross")
        self.assertEqual(sim.fills, [])
        self.assertEqual(sim.orders, {})
        self.assertTrue(sim.submit(buy(self.ticker, "no", 0.55, 2, post_only=True), t).startswith("resting:"), "NO ask is 0.60")

    def test_cancel_touches_only_the_strategys_own_orders(self):
        sim = self.build([candle(self.open + MINUTE, 0.40, 0.45)])
        t = self.open + 2 * MINUTE
        mine = sim.submit(buy(self.ticker, "yes", 0.30, 2), t).split(":", 1)[1]
        theirs = sim.add_order({**sim.orders[mine], "order_id": "foreign-1", "strategy": "someone_else"})["order_id"]
        self.assertEqual(sim.cancel([mine, theirs, "nonexistent"], "tester"), 1)
        self.assertNotIn(mine, sim.orders)
        self.assertIn(theirs, sim.orders)
        strategies = {o["strategy"] for o in sim.context(t)["open_orders"]}
        self.assertEqual(strategies, {"someone_else"})

    def test_settlement_happens_at_close_and_never_before(self):
        sim = self.build([candle(self.open + MINUTE, 0.52, 0.55)], result="yes")
        t = self.open + 5 * MINUTE
        sim.submit(buy(self.ticker, "yes", 0.55, 10), t)
        sim.advance(self.open + HOUR - 1)
        self.assertEqual(sim.closed, [])
        self.assertEqual(len(sim.positions), 1)
        sim.advance(self.open + HOUR)
        self.assertEqual(len(sim.closed), 1)
        self.assertEqual(sim.positions, {})
        self.assertAlmostEqual(sim.closed[0]["pnl"], 10 * (1.0 - 0.55) - kalshi_taker_fee(0.55, 10))
        self.assertEqual(sim.closed[0]["ts"], self.open + HOUR)

    def test_resting_orders_expire_at_close(self):
        sim = self.build([candle(self.open + MINUTE, 0.40, 0.45)])
        sim.submit(buy(self.ticker, "yes", 0.20, 2), self.open + 2 * MINUTE)
        sim.advance(self.open + HOUR)
        self.assertEqual(sim.orders, {})
        self.assertEqual(sim.counts["expired"], 1)

    def test_the_kalshi_fee_is_charged_to_the_hundredth_of_a_cent_as_on_the_tape(self):
        # Sept 16, 2026 live fills: 1 @ 0.02, 22 @ 0.51, 60 @ 0.31.
        self.assertEqual(kalshi_taker_fee(0.02, 1), 0.0014)
        self.assertEqual(kalshi_taker_fee(0.51, 22), 0.3849)
        self.assertEqual(kalshi_taker_fee(0.31, 60), 0.8984)
        self.assertEqual(kalshi_taker_fee(0.50, 4), 0.07, "exactly on the grid is not rounded up again")

    def test_a_resting_order_expires_at_its_stated_expiry_and_a_later_candle_cannot_fill_it(self):
        sub = self.open + 10 * MINUTE
        minutes = [
            candle(self.open + 10 * MINUTE, 0.40, 0.50),
            candle(self.open + 11 * MINUTE, 0.40, 0.50),
            candle(self.open + 13 * MINUTE, 0.40, 0.50, ask_low=0.40),  # trades through after the expiry
        ]
        sim = self.build(minutes)
        status = sim.submit(buy(self.ticker, "yes", 0.45, 4, expire_after_seconds=120), sub)
        self.assertTrue(status.startswith("resting:"), status)
        self.assertEqual(sim.orders[status.split(":", 1)[1]]["expires_ts"], sub + 120)
        sim.advance(self.open + 13 * MINUTE)
        self.assertEqual((sim.fills, sim.orders, sim.counts["expired"]), ([], {}, 1))
        # The same bid with no expiry fills on that candle.
        control = self.build(minutes)
        control.submit(buy(self.ticker, "yes", 0.45, 4), sub)
        control.advance(self.open + 13 * MINUTE)
        self.assertEqual(len(control.fills), 1)

    def test_a_stated_expires_at_is_clamped_and_a_bad_expiry_is_refused(self):
        sim = self.build([candle(self.open + MINUTE, 0.40, 0.50)])
        t = self.open + 2 * MINUTE
        far = sim.submit(buy(self.ticker, "yes", 0.30, 2, expires_at=iso(t + 30 * 24 * HOUR)), t)
        near = sim.submit(buy(self.ticker, "yes", 0.31, 2, expires_at=iso(t + 5)), t)
        self.assertEqual(sim.orders[far.split(":", 1)[1]]["expires_ts"], t + 48 * HOUR)
        self.assertEqual(sim.orders[near.split(":", 1)[1]]["expires_ts"], t + 120)
        # A stamp the floor's parser refuses is refused here as well: a bare date, a time without
        # seconds, the basic form, a number.
        for extra in ({"expire_after_seconds": 60}, {"expire_after_seconds": "600"}, {"expires_at": "soon"},
                      {"expires_at": iso(t + 600), "expire_after_seconds": 600}, {"expires_at": iso(t + 3600)[:10]},
                      {"expires_at": iso(t + 3600)[:16] + "Z"}, {"expires_at": iso(t + 3600).replace("-", "").replace(":", "")},
                      {"expires_at": t + 3600}):
            self.assertTrue(sim.submit(buy(self.ticker, "yes", 0.30, 2, **extra), t).startswith("rejected:"), extra)

    def test_the_backtest_reads_an_expiry_exactly_as_the_floor_does(self):
        # Sept 17, 2026: a stamp the backtest clamped but the floor refused would make a strategy
        # that trades in its backtest place nothing once deployed.
        from ltcm import tools
        from ltcm.backtest import _expiry_ts

        t = self.open + 2 * MINUTE
        stamp = iso(t + 3600)
        stated = [stamp, stamp[:10], stamp[:16] + "Z", stamp[:16], stamp.replace("-", "").replace(":", ""),
                  stamp[:-1] + ".250Z", stamp[:-1] + "+00:00", stamp[:-1] + "+02:00", stamp.replace("T", " "),
                  stamp[:-1], stamp.lower(), "soon", "", t + 3600, None]
        for value in stated:
            session = tools.ToolSession(session_id="s", desk_id="d", now=iso(t))
            try:
                floor = tools._expiry({"expires_at": value}, session)
            except tools.ToolError:
                floor = "refused"
            ours, refusal = _expiry_ts({"expires_at": value}, t)
            if floor == "refused":
                self.assertIsNotNone(refusal, value)
            elif floor is None:
                self.assertEqual((ours, refusal), (None, None), value)
            else:
                self.assertEqual(ours, parse_time(floor), value)

    def test_intent_notional_is_capped_at_ten_times_learning(self):
        sim = self.build([candle(self.open + MINUTE, 0.40, 0.50)])
        sim.submit(buy(self.ticker, "yes", 0.50, 10_000), self.open + 2 * MINUTE)
        self.assertEqual(sim.fills[-1]["quantity"], 200.0)


def coinbase_series(start, count, seconds, base=100.0, wiggle=0.0):
    out = []
    for i in range(count):
        close = base * (1.0 + wiggle * math.sin(i))
        out.append({"ts": int(start + i * seconds), "open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": 10.0})
    return out


class CryptoTests(unittest.TestCase):
    def setUp(self):
        self.start = T0
        self.end = T0 + 6 * HOUR
        bars = coinbase_series(T0 - 30 * HOUR, 36 * 12, 300)
        # One dip below 99.5 in the candle starting at T0 + 1h.
        for bar in bars:
            if bar["ts"] == T0 + HOUR:
                bar["low"] = 99.0
        self.history = FakeHistory(coinbase={("BTC-USD", "FIVE_MINUTE"): bars})
        self.data = DataSet(self.history, self.start, self.end, say=lambda text: None, notes=[])
        self.sim = simulator(self.data)

    def intent(self, side, price, quantity, **extra):
        return {"instrument": {"asset_class": "crypto", "symbol": "BTC-USD"}, "side": side, "quantity": str(quantity), "order_type": "limit", "limit_price": str(price), **extra}

    def test_bars_and_quotes_never_include_a_candle_still_open(self):
        kit = BacktestKit(self.data, self.sim, T0 + 7 * MINUTE, products=None, half_spread=0.0001)
        bars = kit.bars("BTC-USD", "5m", 3)
        self.assertEqual(bars[-1]["start"], iso(T0), "the candle starting at T0 closed at T0+5m; the next one is still open")
        quote = kit.quote("BTC-USD")
        self.assertAlmostEqual(float(quote["ask"]), 100.0 * 1.0001)
        self.assertAlmostEqual(float(quote["bid"]), 100.0 * 0.9999)

    def test_marketable_limit_takes_with_the_taker_fee_and_a_resting_bid_fills_on_a_later_low(self):
        self.assertEqual(self.sim.submit(self.intent("buy", 101, 0.05), T0), "filled")
        fill = self.sim.fills[-1]
        self.assertAlmostEqual(fill["price"], 100.01)
        self.assertAlmostEqual(fill["fee"], 0.05 * 100.01 * 0.006)
        self.assertEqual(self.sim.submit(self.intent("buy", 101, 0.05, post_only=True), T0), "rejected:post-only order would cross")
        status = self.sim.submit(self.intent("buy", 99.5, 0.05, post_only=True), T0 + 30 * MINUTE)
        self.assertTrue(status.startswith("resting:"))
        self.sim.advance(T0 + HOUR)
        self.assertEqual(len(self.sim.fills), 1)
        self.sim.advance(T0 + HOUR + 5 * MINUTE)
        self.assertEqual(len(self.sim.fills), 2)
        self.assertAlmostEqual(self.sim.fills[-1]["price"], 99.5)
        self.assertAlmostEqual(self.sim.fills[-1]["fee"], 0.05 * 99.5 * 0.0025)

    def test_a_resting_bid_that_expires_before_the_dip_never_fills(self):
        # The dip below 99.5 is in the candle starting at T0 + 1h; the bid expires at T0 + 50m.
        status = self.sim.submit(self.intent("buy", 99.5, 0.05, post_only=True, expire_after_seconds=20 * 60), T0 + 30 * MINUTE)
        self.assertTrue(status.startswith("resting:"), status)
        self.sim.advance(T0 + HOUR + 5 * MINUTE)
        self.assertEqual((self.sim.fills, self.sim.orders, self.sim.counts["expired"]), ([], {}, 1))

    def test_open_positions_are_marked_at_the_end_and_the_time_stop_closes(self):
        self.sim.submit(self.intent("buy", 101, 0.05, holding_period_hours=2), T0)
        self.sim.advance(T0 + HOUR)
        self.assertEqual(self.sim.closed, [])
        self.sim.advance(T0 + 2 * HOUR)
        self.assertEqual(len(self.sim.closed), 1, "the floor's time stop sells a crypto position")
        self.sim.submit(self.intent("buy", 101, 0.05), T0 + 3 * HOUR)
        marks = self.sim.finish(self.end)
        self.assertEqual(marks["open_positions"], 1)
        self.assertLess(marks["unrealized"], 0, "a round trip through the spread and the fee is a loss")

    def test_a_sell_of_a_coin_not_held_is_rejected(self):
        self.assertEqual(self.sim.submit(self.intent("sell", 99, 1), T0), "rejected:sell of a coin not held")


FAVORITE_START = T0
FAVORITE_END = T0 + 30 * HOUR


def favorites_history():
    markets, candles = [], {}
    for i in range(4):
        ticker = f"KXFAV{i}-26SEP11-X"
        open_ts = T0 - 20 * HOUR
        close = T0 + (12 + 3 * i) * HOUR
        markets.append(market_row(ticker, open_ts, close, result="no", volume=20_000, title=f"Longshot {i}"))
        hourly, minutes = [], []
        ts = open_ts + HOUR
        hour = 0
        fine_from = math.floor((close - 90 * MINUTE) / HOUR) * HOUR
        while ts <= fine_from:
            odd = hour % 2 == 1
            hourly.append(candle(ts, 0.07 if odd else 0.03, 0.08 if odd else 0.06, volume=800.0))
            ts += HOUR
            hour += 1
        ts = fine_from + MINUTE
        while ts <= close:
            minutes.append(candle(ts, 0.03, 0.06, volume=5.0))
            ts += 10 * MINUTE
        candles[(ticker, 60)] = hourly
        candles[(ticker, 1)] = minutes
    # A market that settles YES against the favorite, to prove losses are booked too.
    ticker = "KXFAVLOSE-26SEP11-Y"
    open_ts, close = T0 - 20 * HOUR, T0 + 20 * HOUR
    markets.append(market_row(ticker, open_ts, close, result="yes", volume=30_000, title="Upset"))
    candles[(ticker, 60)] = [candle(open_ts + (h + 1) * HOUR, 0.07 if h % 2 else 0.03, 0.08 if h % 2 else 0.06, volume=900.0) for h in range(38)]
    candles[(ticker, 1)] = []
    return FakeHistory(markets, candles)


class EndToEndTests(unittest.TestCase):
    def test_kalshi_favorites_runs_on_a_synthetic_board_and_trades(self):
        history = favorites_history()
        report = run_backtest(
            {"strategy": "kalshi_favorites", "start": iso(FAVORITE_START), "end": iso(FAVORITE_END), "step_minutes": 15, "verbose": False},
            history=history,
        )
        self.assertEqual(report["errors"], 0, report["notes"])
        self.assertGreater(report["fills"], 0)
        self.assertGreater(report["trades"], 0)
        self.assertEqual(report["settled"], report["trades"])
        self.assertEqual(report["maker_fills"], report["fills"], "post-only bids fill as a maker")
        self.assertEqual(report["fees_usd"], 0.0)
        self.assertEqual(len(report["trade_pnls"]), report["trades"])
        self.assertTrue(any(p < 0 for p in report["trade_pnls"]), "the upset is booked as a loss")
        self.assertLess(report["wins"], report["trades"])
        self.assertAlmostEqual(report["pnl_usd"], round(sum(report["trade_pnls"]), 4), places=3)
        self.assertIn("the settled board was loaded", report["notes"])
        settled_calls = [c for c in history.calls if c[0] == "settled"]
        self.assertTrue(all(c[1] is None for c in settled_calls), "kalshi_markets loads the whole board")
        lo, hi = report["ci95_mean_pnl"]
        self.assertLessEqual(lo, hi)
        self.assertEqual(sum(d["trades"] for d in report["daily"]), report["trades"])
        for key in ("strategy", "params", "start", "end", "steps", "trades", "fills", "settled", "wins", "notional_usd", "pnl_usd",
                    "fees_usd", "return_on_notional", "max_drawdown_usd", "daily", "trade_pnls", "ci95_mean_pnl", "errors", "notes"):
            self.assertIn(key, report)
        again = run_backtest(
            {"strategy": "kalshi_favorites", "start": iso(FAVORITE_START), "end": iso(FAVORITE_END), "step_minutes": 15, "verbose": False},
            history=favorites_history(),
        )
        self.assertEqual(again["trade_pnls"], report["trade_pnls"], "deterministic")
        self.assertEqual(again["ci95_mean_pnl"], report["ci95_mean_pnl"])

    def test_kalshi_favorites_v2_replays_from_the_backtest_books(self):
        v2 = {"book_pricing": True, "keep_queue": True, "band_exit": True, "max_open_per_cluster": 2, "expire_seconds": 5400}
        report = run_backtest(
            {"strategy": "kalshi_favorites", "params": v2, "start": iso(FAVORITE_START), "end": iso(FAVORITE_END), "step_minutes": 15, "verbose": False},
            history=favorites_history(),
        )
        self.assertEqual(report["errors"], 0, report["notes"])
        self.assertGreater(report["fills"], 0, "bids priced from the candle book rest and fill")
        self.assertEqual(report["maker_fills"], report["fills"])

    def test_hourly_ranges_runs_on_synthetic_thresholds_and_takes_the_cheap_side(self):
        start, end = T0 + 12 * HOUR, T0 + 16 * HOUR
        bars = coinbase_series(start - 30 * HOUR, 40 * 12, 300, base=100_000.0, wiggle=0.002)
        markets, candles = [], {}
        for h in range(4):
            open_ts = start + h * HOUR
            close = open_ts + HOUR
            for k, strike in enumerate((99_999.99, 100_249.99)):
                ticker = f"KXBTCD-26SEP10{12 + h:02d}-T{strike:.2f}"
                row = market_row(ticker, open_ts, close, result="yes" if k == 0 else "no", volume=5000,
                                 title="Bitcoin price", yes_sub_title=f"${strike + 0.01:,.0f} or above",
                                 strike_type="greater", floor_strike=strike)
                markets.append(row)
                # At the money priced at 0.30 (cheap YES); the out-of-the-money one fairly.
                bid, ask = (0.28, 0.30) if k == 0 else (0.05, 0.07)
                candles[(ticker, 1)] = [candle(open_ts + m * MINUTE, bid, ask, volume=3.0) for m in range(1, 61)]
        history = FakeHistory(markets, candles, {("BTC-USD", "FIVE_MINUTE"): bars})
        report = run_backtest(
            {"strategy": "hourly_ranges", "params": {"series": ["KXBTCD"]}, "start": iso(start), "end": iso(end), "step_minutes": 5, "verbose": False},
            history=history,
        )
        self.assertEqual(report["errors"], 0, report["notes"])
        self.assertGreater(report["trades"], 0, report)
        self.assertEqual(report["fills"], report["trades"])
        self.assertGreater(report["fees_usd"], 0, "taking the ask pays Kalshi's fee")
        self.assertGreater(report["pnl_usd"], 0, "cheap YES that settles YES")
        self.assertIn("series loaded: KXBTCD", report["notes"])
        self.assertTrue(all(c[1] == "KXBTCD" for c in history.calls if c[0] == "settled"))
        self.assertTrue(any(c[0] == "coinbase" and c[4] == "FIVE_MINUTE" for c in history.calls))

    def test_weather_is_unsupported(self):
        report = run_backtest({"strategy": "daily_temps", "verbose": False, "start": iso(T0), "end": iso(T0 + 24 * HOUR)}, history=FakeHistory())
        self.assertIn("weather", report["unsupported"])
        self.assertEqual(report["trades"], 0)
        code = "def decide(kit, params):\n    try:\n        kit.weather('NYC')\n    except Exception:\n        pass\n    return []\n"
        report = run_backtest({"strategy": "custom", "code": code, "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR)}, history=FakeHistory(), trusted_code=True)
        self.assertIn("NWS", report["unsupported"], "a strategy that swallows the error is still unsupported")

    def test_strategy_errors_are_counted_never_fatal(self):
        code = "def decide(kit, params):\n    raise RuntimeError('boom')\n"
        report = run_backtest({"strategy": "broken", "code": code, "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR), "step_minutes": 15}, history=FakeHistory(), trusted_code=True)
        self.assertEqual(report["steps"], 5)
        self.assertEqual(report["errors"], 5)
        self.assertTrue(any("boom" in n for n in report["notes"]))
        report = run_backtest({"strategy": "bad", "code": "def decide(:\n", "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR)}, history=FakeHistory(), trusted_code=True)
        self.assertEqual(report["errors"], 1)
        self.assertEqual(report["steps"], 0)

    def test_a_strategy_printing_does_not_touch_stdout(self):
        code = "def decide(kit, params):\n    print('chatty')\n    return []\n"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            run_backtest({"strategy": "chatty", "code": code, "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR)}, history=FakeHistory(), trusted_code=True)
        self.assertEqual(out.getvalue(), "")


class MetricsTests(unittest.TestCase):
    def test_split_report_is_chronological(self):
        report = {"trade_pnls": [1.0, 2.0, 3.0, 4.0, 5.0, -6.0], "trade_notionals": [10.0] * 6, "seed": 7}
        split = split_report(report)
        self.assertEqual(split["in_sample"]["trades"], 4)
        self.assertEqual(split["in_sample"]["pnl_usd"], 10.0)
        self.assertEqual(split["in_sample"]["return_on_notional"], 0.25)
        self.assertEqual(split["out_of_sample"]["trades"], 2)
        self.assertEqual(split["out_of_sample"]["pnl_usd"], -1.0)
        self.assertEqual(split["out_of_sample"]["return_on_notional"], -0.05)
        lo, hi = split["in_sample"]["ci95_mean_pnl"]
        self.assertTrue(1.0 <= lo <= hi <= 4.0)
        half = split_report(report, fraction=0.5)
        self.assertEqual(half["in_sample"]["pnl_usd"], 6.0)
        self.assertEqual(split_report({"trade_pnls": []})["in_sample"]["ci95_mean_pnl"], [None, None])

    def test_bootstrap_is_seeded_and_drawdown_reads_the_closed_curve(self):
        values = [0.5, -1.0, 0.25, 0.75, -0.2, 0.1]
        self.assertEqual(bootstrap_ci(values, 7), bootstrap_ci(values, 7))
        lo, hi = bootstrap_ci(values, 7)
        self.assertLess(lo, sum(values) / len(values))
        self.assertGreater(hi, sum(values) / len(values))
        self.assertEqual(max_drawdown([1.0, -2.0, 0.5, -1.0, 3.0]), 2.5)
        self.assertEqual(max_drawdown([]), 0.0)

    def test_kalshi_plan_reads_the_strategy_needs(self):
        ns = {"DEFAULTS": {"series": "all"}, "CRYPTO_SERIES": {"KXBTC": "BTC-USD", "KXETHD": "ETH-USD"}}
        self.assertEqual(kalshi_plan("kit.kalshi_series(s)", {}, {}, ns), ("series", ["KXBTC", "KXETHD"]))
        self.assertEqual(kalshi_plan("kit.kalshi_series(s)", {"series": ["KXBTCD"]}, {}, ns), ("series", ["KXBTCD"]))
        self.assertEqual(kalshi_plan("kit.kalshi_markets()", {}, {}, {}), ("board", []))
        self.assertEqual(kalshi_plan("kit.kalshi_markets()", {}, {"series": ["kxa"]}, {}), ("series", ["KXA"]))
        self.assertEqual(kalshi_plan("kit.kalshi_series('KXHIGHNY')", {}, {}, {}), ("series", ["KXHIGHNY"]))
        self.assertEqual(kalshi_plan("kit.bars('BTC-USD')", {}, {}, {}), ("none", []))


class CliTests(unittest.TestCase):
    def run_main(self, argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("ltcm.history.History", lambda **kwargs: FakeHistory()), mock.patch("ltcm.backtest.in_sandbox", lambda: True):
            code = main(argv)
        return code, out.getvalue()

    def test_the_cli_prints_exactly_one_result_line(self):
        spec = {"strategy": "quiet", "code": "def decide(kit, params):\n    print('noise')\n    return []\n", "start": iso(T0), "end": iso(T0 + HOUR)}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            code, stdout = self.run_main(["--spec", str(path)])
        self.assertEqual(code, 0)
        lines = stdout.splitlines()
        self.assertEqual(len(lines), 1, stdout)
        self.assertTrue(lines[0].startswith(RESULT_PREFIX))
        report = json.loads(lines[0][len(RESULT_PREFIX):])
        self.assertEqual(report["steps"], 5)
        code, stdout = self.run_main([], stdin=json.dumps(spec))
        self.assertEqual(code, 0)
        self.assertEqual(len(stdout.splitlines()), 1)
        self.assertIn("split", report)
        code, stdout = self.run_main([], stdin=json.dumps({**spec, "compact": True}))
        compact = json.loads(stdout.splitlines()[0][len(RESULT_PREFIX):])
        self.assertNotIn("trade_pnls", compact)
        self.assertIn("in_sample", compact["split"])

    def test_a_bad_spec_is_a_report_not_a_traceback(self):
        for argv, stdin in (([], "not json"), (["--spec", "/nonexistent/spec.json"], ""), (["--bogus"], "")):
            code, stdout = self.run_main(argv, stdin)
            self.assertEqual(code, 0)
            lines = stdout.splitlines()
            self.assertEqual(len(lines), 1)
            report = json.loads(lines[0][len(RESULT_PREFIX):])
            self.assertEqual(report["errors"], 1)


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, headers=None, timeout=20):
        self.urls.append(url)
        status, payload = self.responses.pop(0)
        return status, {}, json.dumps(payload).encode("utf-8")


def raw_market(ticker, *, volume="600.00", result="no"):
    return {
        "ticker": ticker, "event_ticker": "-".join(ticker.split("-")[:2]), "title": "t", "yes_sub_title": "s",
        "status": "finalized", "result": result, "open_time": "2026-09-10T10:00:00Z", "close_time": "2026-09-10T11:00:00Z",
        "yes_bid_dollars": "0.0000", "yes_ask_dollars": "1.0000", "volume_fp": volume, "settlement_value_dollars": "0.0000",
        "strike_type": "greater", "floor_strike": 100.5,
    }


class HistoryTests(unittest.TestCase):
    def test_settled_markets_page_filter_and_parse(self):
        transport = Transport([
            (429, {}),
            (200, {"markets": [raw_market("KXA-1-X"), raw_market("KXMVE-1-Y"), raw_market("KXA-1-Z", volume="10.00")], "cursor": "next"}),
            (200, {"markets": [raw_market("KXA-2-X", result="yes")], "cursor": ""}),
        ])
        sleeps = []
        history = History(transport, min_interval=0, sleep=sleeps.append, verbose=False)
        rows = history.kalshi_settled("KXA", start_ts=T0, end_ts=T0 + HOUR, min_volume=500)
        self.assertEqual([r["ticker"] for r in rows], ["KXA-1-X", "KXA-2-X"])
        self.assertEqual(rows[1]["result"], "yes")
        self.assertEqual(str(rows[0]["floor_strike"]), "100.5")
        self.assertEqual(rows[0]["settlement_value"], 0.0)
        self.assertEqual(history.requests, 3)
        self.assertEqual(history.rate_limited, 1)
        self.assertEqual(len(sleeps), 1, "a 429 is retried after a pause")
        self.assertIn("status=settled", transport.urls[0])
        self.assertIn("mve_filter=exclude", transport.urls[0])
        self.assertIn("cursor=next", transport.urls[-1])

    def test_batch_candles_respect_the_endpoint_limits(self):
        tickers = [f"KXA-1-{i}" for i in range(250)]
        responses = []
        for chunk in (tickers[0:100], tickers[100:200], tickers[200:250]):
            responses.append((200, {"markets": [{"market_ticker": t, "candlesticks": [
                {"end_period_ts": T0 + 60, "yes_bid": {"close_dollars": "0.4100", "high_dollars": "0.4200", "low_dollars": "0.4", "open_dollars": "0.4"},
                 "yes_ask": {"close_dollars": "0.4500"}, "price": {}, "volume_fp": "3.00", "open_interest_fp": "9.00"}]} for t in chunk]}))
        transport = Transport(responses)
        history = History(transport, min_interval=0, verbose=False)
        found = history.kalshi_candles_many(tickers, start_ts=T0, end_ts=T0 + 60 * MINUTE, period_minutes=1)
        self.assertEqual(len(transport.urls), 3, "100 markets a call")
        self.assertEqual(found["KXA-1-7"][0]["yes_bid_close"], 0.41)
        self.assertEqual(found["KXA-1-7"][0]["yes_bid_high"], 0.42)
        self.assertEqual(found["KXA-1-7"][0]["yes_ask_close"], 0.45)
        self.assertIsNone(found["KXA-1-7"][0]["price_close"])
        self.assertIsNone(found["KXA-1-7"][0]["price_high"])
        transport = Transport([(200, {"markets": []})] * 20)
        History(transport, min_interval=0, verbose=False).kalshi_candles_many(tickers[:60], start_ts=T0, end_ts=T0 + 400 * MINUTE, period_minutes=1)
        self.assertGreater(len(transport.urls), 1, "markets x periods stays under 10,000 a call")

    def test_coinbase_candles_are_chunked_ascending_and_bounded(self):
        start = (T0 // 300) * 300
        rows = [{"start": str(int(start + i * 300)), "open": "1", "high": "2", "low": "0.5", "close": "1.5", "volume": "3"} for i in range(400)]
        first = [r for r in rows if int(r["start"]) < (start // 90000 + 1) * 90000]
        transport = Transport([(200, {"candles": list(reversed(rows))})] * 3)
        history = History(transport, min_interval=0, verbose=False)
        found = history.coinbase_candles("BTC-USD", start_ts=start, end_ts=start + 399 * 300)
        self.assertEqual([c["ts"] for c in found], sorted(c["ts"] for c in found))
        self.assertEqual(len(found), 400)
        self.assertTrue(first)
        for url in transport.urls:
            query = dict(part.split("=") for part in url.split("?", 1)[1].split("&"))
            self.assertLess((int(query["end"]) - int(query["start"])) / 300, 350)

    def test_the_disk_cache_never_outgrows_its_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DiskCache(tmp, 64 * 1024)
            import os

            for i in range(200):
                cache.put(f"url-{i}", os.urandom(4000))
            total = sum(p.stat().st_size for p in Path(tmp).glob("*.z"))
            self.assertLessEqual(total, 64 * 1024)
            self.assertIsNone(cache.get("url-0"), "the oldest went first")
            self.assertIsNotNone(cache.get("url-199"))

    def test_settled_responses_in_the_past_are_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = Transport([(200, {"markets": [raw_market("KXA-1-X")], "cursor": ""})])
            history = History(transport, cache_dir=tmp, min_interval=0, clock=lambda: T0 + 30 * 86400, verbose=False)
            history.kalshi_settled("KXA", start_ts=T0, end_ts=T0 + HOUR)
            again = history.kalshi_settled("KXA", start_ts=T0, end_ts=T0 + HOUR)
            self.assertEqual(len(again), 1)
            self.assertEqual(history.requests, 1)
            self.assertEqual(history.cache_hits, 1)


# ----------------------------------------------------------------- review regressions (Sept 16)

BUY_EVERY_BUCKET = """
def decide(kit, params):
    out = []
    held = {p["market_id"] for p in kit.context["positions"]}
    for m in kit.kalshi_series("KXBUCK"):
        if m["ticker"] in held or m["yes_ask"] is None:
            continue
        out.append({"instrument": {"asset_class": "event", "symbol": m["ticker"], "market_id": m["ticker"], "right": "yes"},
                    "side": "buy", "quantity": "1", "order_type": "limit", "limit_price": str(m["yes_ask"]), "rationale": "x"})
    return out[:5]
"""


def bucket_events(events, buckets, *, winner_volume, seed_shift=0):
    """`events` hourly events of `buckets` identical buckets; one wins, and (unless its volume is
    the same as the rest) it traded far more by its close, as winning buckets do."""
    markets, candles = [], {}
    for e in range(events):
        open_ts = T0 + e * HOUR
        close = open_ts + HOUR
        winner = (e * 7 + seed_shift) % buckets
        for b in range(buckets):
            ticker = f"KXBUCK-26SEP10{e:02d}-B{b:02d}"
            won = b == winner
            markets.append(market_row(ticker, open_ts, close, result="yes" if won else "no", volume=winner_volume if won else 10))
            candles[(ticker, 1)] = [candle(open_ts + m * MINUTE, 0.03, 0.04, volume=1) for m in range(1, 60)]
    return markets, candles


class SelectionTests(unittest.TestCase):
    """Finding 1: a capped listing chose markets by lifetime volume, which keeps the winners."""

    def load(self, markets, candles, *, board, cap):
        data = DataSet(FakeHistory(markets, candles), T0, T0 + 30 * HOUR, say=lambda text: None, notes=[])
        data.load_kalshi(series=None if board else ["KXBUCK"], board=board, max_markets=cap, max_pages=20, seed=7)
        return data

    def test_a_capped_listing_never_keeps_markets_by_final_volume_or_result(self):
        for board in (False, True):
            loud = self.load(*bucket_events(24, 10, winner_volume=1_000_000), board=board, cap=24)
            quiet = self.load(*bucket_events(24, 10, winner_volume=10, seed_shift=3), board=board, cap=24)
            self.assertEqual(len(loud.markets), 24)
            self.assertEqual(sorted(loud.markets), sorted(quiet.markets), "volume and result never pick a market")
            self.assertEqual(len({m.event for m in loud.markets.values()}), 24, "every event keeps a draw before any keeps two")
            winners = sum(1 for m in loud.markets.values() if m.payout_yes == 1.0)
            self.assertLessEqual(winners, 8, f"about one in ten kept should be a winner, not {winners} of 24")
            self.assertTrue(any("never by volume or result" in n for n in loud.notes))

    def test_the_series_volume_draw_keeps_whole_events_of_the_busiest_series_first(self):
        """Sept 18, 2026: the even draw showed a favorites replay one market in ninety."""
        loud_markets, loud_candles = bucket_events(4, 10, winner_volume=1_000_000)
        quiet_markets, quiet_candles = bucket_events(4, 10, winner_volume=10, seed_shift=3)
        for row in quiet_markets:
            row["ticker"] = row["ticker"].replace("KXBUCK", "KXQUIET"); row["event_ticker"] = row["event_ticker"].replace("KXBUCK", "KXQUIET")
        quiet_candles = {(k[0].replace("KXBUCK", "KXQUIET"), k[1]): v for k, v in quiet_candles.items()}
        data = DataSet(FakeHistory(loud_markets + quiet_markets, {**loud_candles, **quiet_candles}), T0, T0 + 30 * HOUR, say=lambda text: None, notes=[])
        data.load_kalshi(series=None, board=True, max_markets=25, max_pages=20, seed=7, draw="series_volume")
        kept = list(data.markets.values())
        self.assertEqual(len(kept), 25)
        self.assertTrue(all(m.series == "KXBUCK" for m in kept[:20]) or sum(1 for m in kept if m.series == "KXBUCK") >= 20, "the busy series' events come first")
        events = {}
        for m in kept:
            events.setdefault(m.event, 0); events[m.event] += 1
        self.assertGreaterEqual(sum(1 for n in events.values() if n == 10), 2, "whole events, ten buckets each")
        winners = sum(1 for m in kept if m.series == "KXBUCK" and m.payout_yes == 1.0)
        self.assertLessEqual(winners, 3, "a bucket is never kept for being the winner")
        self.assertTrue(any("busiest series first" in n for n in data.notes))

    def test_the_event_volume_draw_keeps_the_busiest_whole_events_first(self):
        loud_markets, loud_candles = bucket_events(4, 10, winner_volume=1_000_000)
        quiet_markets, quiet_candles = bucket_events(4, 10, winner_volume=10, seed_shift=3)
        for row in quiet_markets:
            row["ticker"] = row["ticker"].replace("KXBUCK", "KXQUIET"); row["event_ticker"] = row["event_ticker"].replace("KXBUCK", "KXQUIET")
        quiet_candles = {(k[0].replace("KXBUCK", "KXQUIET"), k[1]): v for k, v in quiet_candles.items()}
        data = DataSet(FakeHistory(loud_markets + quiet_markets, {**loud_candles, **quiet_candles}), T0, T0 + 30 * HOUR, say=lambda text: None, notes=[])
        data.load_kalshi(series=None, board=True, max_markets=30, max_pages=20, seed=7, draw="event_volume")
        kept = list(data.markets.values())
        self.assertEqual(len(kept), 30)
        self.assertGreaterEqual(sum(1 for m in kept if m.series == "KXBUCK"), 30, "the four busy events fill the cap before any quiet one")
        winners = sum(1 for m in kept if m.payout_yes == 1.0)
        self.assertLessEqual(winners, 3, "whole events: a bucket is never kept for winning")
        self.assertTrue(any("busiest events first" in n for n in data.notes))

    def test_the_draw_is_seeded_and_a_bigger_cap_keeps_a_superset(self):
        data = self.load(*bucket_events(6, 10, winner_volume=5), board=False, cap=3000)
        pool = list(data.markets.values())
        small = {m.ticker for m in sample_markets(pool, 12, 7)}
        big = {m.ticker for m in sample_markets(list(reversed(pool)), 30, 7)}
        self.assertLessEqual(small, big)
        self.assertEqual(small, {m.ticker for m in sample_markets(pool, 12, 7)})
        self.assertNotEqual(small, {m.ticker for m in sample_markets(pool, 12, 8)})

    def test_a_strategy_buying_every_listed_bucket_is_not_paid_by_the_cap(self):
        markets, candles = bucket_events(1, 50, winner_volume=90_000)
        spec = {"strategy": "buckets", "code": BUY_EVERY_BUCKET, "series": ["KXBUCK"], "start": iso(T0), "end": iso(T0 + 2 * HOUR),
                "step_minutes": 5, "max_markets": 5, "verbose": False, "min_volume": 500}
        loud = run_backtest(spec, history=FakeHistory(markets, candles), trusted_code=True)
        flat = run_backtest(spec, history=FakeHistory(*bucket_events(1, 50, winner_volume=10)), trusted_code=True)
        self.assertEqual(loud["markets_loaded"], 5)
        self.assertEqual(loud["trade_pnls"], flat["trade_pnls"], "the winner's final volume changes nothing")
        self.assertTrue(any("min_volume ignored" in n for n in loud["notes"]))


PEEK = """
def decide(kit, params):
    out = []
    for m in kit.kalshi_series("KXBUCK"):
        won = kit._data.markets[m["ticker"]].payout_yes == 1.0
        out.append({"instrument": {"asset_class": "event", "symbol": m["ticker"], "market_id": m["ticker"], "right": "yes" if won else "no"},
                    "side": "buy", "quantity": "10", "order_type": "limit", "limit_price": "0.99", "rationale": "x"})
    return out[:5]
"""


class IsolationTests(unittest.TestCase):
    """Finding 2: the kit carried the settled history one attribute away, in the caller's process."""

    def test_a_strategy_reading_the_kits_history_is_refused(self):
        markets, candles = bucket_events(2, 10, winner_volume=10)
        report = run_backtest({"strategy": "peek", "code": PEEK, "series": ["KXBUCK"], "start": iso(T0), "end": iso(T0 + 3 * HOUR),
                               "verbose": False}, history=FakeHistory(markets, candles), trusted_code=True)
        self.assertEqual(report["errors"], 1)
        self.assertEqual(report["trades"], 0)
        self.assertTrue(any("._data is not allowed" in n for n in report["notes"]), report["notes"])

    def test_the_screen_refuses_every_way_out_of_decide(self):
        for code in (
            "import gc\ndef decide(kit, params):\n    return []\n",
            "import inspect\ndef decide(kit, params):\n    return []\n",
            "from ltcm import backtest\ndef decide(kit, params):\n    return []\n",
            "import os\ndef decide(kit, params):\n    return []\n",
            "import urllib.request\ndef decide(kit, params):\n    return []\n",
            "def decide(kit, params):\n    return kit.quote.__closure__\n",
            "def decide(kit, params):\n    name = 'context'\n    return getattr(kit, name)\n",
            "def decide(kit, params):\n    return '{0.x}'.format(kit)\n",
            "def decide(kit, params):\n    return __builtins__\n",
            "def decide(kit, params):\n    exit(0)\n",
            "def decide(kit, params):\n    kit.say = print\n",
            "import statistics\ndef decide(kit, params):\n    return statistics.sys\n",
        ):
            with self.assertRaises(CodeRefused, msg=code):
                check_code(code)
        check_code("import math, re\nfrom datetime import datetime\ndef decide(kit, params):\n    return getattr(kit, 'context')\n")

    def test_decide_gets_a_facade_with_no_path_to_the_history(self):
        row, candles = one_hour_market(minute_candles=[candle(T0 + 10 * HOUR + MINUTE, 0.40, 0.45)])
        data = dataset(FakeHistory([row], candles))
        core = BacktestKit(data, simulator(data), T0 + 10 * HOUR + 5 * MINUTE, products=None, half_spread=0.0)
        kit = core.strategy_kit()
        public = {name for name in dir(kit) if not name.startswith("_")}
        self.assertEqual(public, {"context"} | set(KIT_CALLS))
        for name in ("_data", "_sim", "_t", "__dict__"):
            self.assertFalse(hasattr(kit, name), name)
        self.assertEqual(str(kit.kalshi_market("KXTEST-26SEP10-T1")["yes_ask"]), "0.4500")
        self.assertEqual(len(kit.kalshi_series("KXTEST")), 1)
        shown = run_backtest({"strategy": "who", "code": "def decide(kit, params):\n    raise ValueError(repr(kit))\n", "verbose": False,
                              "start": iso(T0), "end": iso(T0 + HOUR)}, history=FakeHistory(), trusted_code=True)
        self.assertTrue(any("StrategyKit(backtest)" in n for n in shown["notes"]), "decide is handed the facade, not the engine's kit")

    def test_model_code_runs_only_in_a_sandbox_unless_the_caller_vouches(self):
        code = "def decide(kit, params):\n    return []\n"
        spec = {"strategy": "mine", "code": code, "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR)}
        with mock.patch("ltcm.backtest.in_sandbox", lambda: False):
            refused = run_backtest(spec, history=FakeHistory())
            self.assertEqual(refused["errors"], 1)
            self.assertTrue(any("runs only in a desk's sandbox" in n for n in refused["notes"]))
            self.assertEqual(run_backtest(spec, history=FakeHistory(), trusted_code=True)["errors"], 0)
            starter = (Path(__file__).resolve().parent.parent / "starters" / "hourly_reversion.py").read_text(encoding="utf-8")
            self.assertNotIn("runs only in", " ".join(run_backtest({**spec, "strategy": "hourly_reversion", "code": starter}, history=FakeHistory())["notes"]))
        with mock.patch("ltcm.backtest.in_sandbox", lambda: True):
            self.assertEqual(run_backtest(spec, history=FakeHistory())["errors"], 0)


class HorizonTests(unittest.TestCase):
    """Finding 3: near `end`, only markets that had closed by `end` existed, favouring early closes."""

    def twins(self):
        listed = T0 + 30 * HOUR
        early = market_row("KXEV-26SEP12-A", T0, T0 + 20 * HOUR + 17, result="yes", can_close_early=True, latest_expiration_time=iso(listed))
        on_time = market_row("KXEV-26SEP12-B", T0, listed, result="no", can_close_early=True, latest_expiration_time=iso(listed))
        soon = market_row("KXEV-26SEP10-C", T0, T0 + 10 * HOUR, result="no")
        later = market_row("KXEV-26SEP12-D", T0 + 25 * HOUR, T0 + 40 * HOUR, result="no")
        candles = {}
        for row in (early, on_time, soon):
            candles[(row["ticker"], 60)] = [candle(T0 + k * HOUR, 0.05, 0.06, volume=2000) for k in range(1, 20)]
        return FakeHistory([early, on_time, soon, later], candles)

    def test_a_market_that_closes_on_schedule_after_end_is_listed_beside_its_early_twin(self):
        history = self.twins()
        data = DataSet(history, T0, T0 + 24 * HOUR, say=lambda text: None, notes=[])
        data.load_kalshi(series=None, board=True, max_markets=3000, max_pages=20)
        self.assertGreaterEqual(max(c[3] for c in history.calls if c[0] == "settled"), T0 + 24 * HOUR + 48 * HOUR - 1)
        self.assertNotIn("KXEV-26SEP12-D", data.markets, "a market opening after end never takes a place in the draw")
        sim = simulator(data)
        kit = BacktestKit(data, sim, T0 + 12 * HOUR, products=None, half_spread=0.0)
        self.assertEqual({r["ticker"] for r in kit.kalshi_markets(max_close_hours=36)}, {"KXEV-26SEP12-A", "KXEV-26SEP12-B"})
        self.assertEqual(sim.submit(buy("KXEV-26SEP12-B", "yes", 0.06, 10), T0 + 12 * HOUR), "filled")
        marks = sim.finish(T0 + 24 * HOUR)
        self.assertEqual(marks["open_positions"], 1, "it trades until end and is marked there, never settled")
        self.assertEqual(sim.counts["settled"], 0)
        self.assertFalse([c for c in history.calls if c[0] == "candles" and c[3] > T0 + 24 * HOUR], "no candles past end")

    def test_an_early_close_listed_past_the_horizon_is_hidden_with_its_twin(self):
        data = DataSet(self.twins(), T0, T0 + 24 * HOUR, say=lambda text: None, notes=[])
        data.load_kalshi(series=None, board=True, max_markets=3000, max_pages=20, horizon_seconds=0)
        self.assertEqual(set(data.markets), {"KXEV-26SEP10-C"}, "A closed inside the window but was listed past it")
        self.assertTrue(any("hidden" in n for n in data.notes))

    def test_listings_stop_where_settlements_may_still_be_arriving(self):
        history = self.twins()
        history.clock = lambda: T0 + 40 * HOUR
        report = run_backtest({"strategy": "kalshi_favorites", "start": iso(T0), "end": iso(T0 + 24 * HOUR), "verbose": False}, history=history)
        self.assertEqual(report["listed_through"], iso(T0 + 16 * HOUR))
        self.assertLessEqual(max(c[3] for c in history.calls if c[0] == "settled"), T0 + 16 * HOUR)
        self.assertTrue(any("complete only through" in n for n in report["notes"]), report["notes"])


class StaleBookTests(unittest.TestCase):
    """Finding 4: a taker filled at an hourly close up to 59 minutes old."""

    ticker = "KXLONG-26SEP10-T1"

    def build(self, minutes):
        row = market_row(self.ticker, T0, T0 + 20 * HOUR, result="no")
        hourly = [candle(T0 + k * HOUR, 0.28, 0.30, volume=100) for k in range(1, 11)]
        hourly.append(candle(T0 + 11 * HOUR, 0.79, 0.80, bid_high=0.80, ask_low=0.30, volume=500))
        data = dataset(FakeHistory([row], {(self.ticker, 60): hourly, (self.ticker, 1): minutes}), series=("KXLONG",))
        return data, simulator(data)

    def test_a_taker_is_judged_on_minute_history_not_a_stale_hourly_close(self):
        data, sim = self.build([candle(T0 + 10 * HOUR + m * MINUTE, 0.79, 0.80, volume=5) for m in range(5, 61)])
        t = T0 + 10 * HOUR + 45 * MINUTE
        sim.advance(t)
        status = sim.submit(buy(self.ticker, "yes", 0.35, 10), t)
        self.assertTrue(status.startswith("resting:"), status)
        self.assertEqual(sim.fills, [], "the ask had been 0.80 since 10:05")
        view = BacktestKit(data, sim, t, products=None, half_spread=0.0).kalshi_market(self.ticker)
        self.assertEqual(str(view["yes_ask"]), "0.8000")

    def test_a_crossing_order_on_a_stale_book_without_minute_history_is_refused(self):
        data, sim = self.build([])
        t = T0 + 10 * HOUR + 45 * MINUTE
        self.assertEqual(sim.submit(buy(self.ticker, "yes", 0.35, 10), t), "rejected:the book is an hourly close over five minutes old with no minute history")
        self.assertTrue(sim.submit(buy(self.ticker, "yes", 0.25, 10), t).startswith("resting:"), "a bid under the book still rests")
        self.assertEqual(sim.submit(buy(self.ticker, "yes", 0.35, 10), T0 + 10 * HOUR + 4 * MINUTE), "filled", "a close four minutes old is fresh")
        self.assertAlmostEqual(sim.fills[-1]["price"], 0.30)


class CryptoFillModelTests(unittest.TestCase):
    """Finding 5: a conservative Coinbase maker filled when the low only touched its limit."""

    def run_model(self, model, low):
        rows = [{"ts": int(T0) + i * 300, "open": 100.5, "high": 101.0, "low": 100.2, "close": 100.5, "volume": 1.0} for i in range(40)]
        rows[20] = {**rows[20], "low": low}
        data = DataSet(FakeHistory(coinbase={("BTC-USD", "FIVE_MINUTE"): rows}), T0 + HOUR, T0 + 3 * HOUR, say=lambda text: None, notes=[])
        sim = Simulator(data, strategy="x", learning_usd=10, half_spread=0.0001, maker_fee=0.0025, taker_fee=0.006, fill_model=model)
        intent = {"instrument": {"asset_class": "crypto", "symbol": "BTC-USD"}, "side": "buy", "quantity": "0.05", "order_type": "limit",
                  "limit_price": "100.0", "post_only": True}
        self.assertTrue(sim.submit(intent, T0 + HOUR).startswith("resting:"))
        sim.advance(T0 + 2 * HOUR)
        return sim.fills

    def test_conservative_needs_a_trade_through_and_touch_takes_the_touch(self):
        self.assertEqual(self.run_model("conservative", 100.0), [])
        self.assertEqual(len(self.run_model("touch", 100.0)), 1)
        fills = self.run_model("conservative", 99.99)
        self.assertEqual(len(fills), 1)
        self.assertAlmostEqual(fills[0]["price"], 100.0)


class ExitTests(unittest.TestCase):
    """Finding 6: a strategy calling sys.exit ended the CLI with no result line."""

    def run_main(self, spec, patches=()):
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("sys.stdin", io.StringIO(json.dumps(spec))))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            stack.enter_context(mock.patch("ltcm.history.History", lambda **kwargs: FakeHistory()))
            stack.enter_context(mock.patch("ltcm.backtest.in_sandbox", lambda: True))
            for patch in patches:
                stack.enter_context(patch)
            code = main([])
        lines = out.getvalue().splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1, out.getvalue())
        self.assertTrue(lines[0].startswith(RESULT_PREFIX))
        return json.loads(lines[0][len(RESULT_PREFIX):])

    def test_a_strategy_raising_system_exit_still_gets_a_result_line(self):
        spec = {"strategy": "quits", "code": "def decide(kit, params):\n    raise SystemExit(0)\n", "start": iso(T0), "end": iso(T0 + HOUR)}
        report = self.run_main(spec)
        self.assertEqual(report["steps"], 5)
        self.assertEqual(report["errors"], 5)
        report = self.run_main({**spec, "code": "raise SystemExit(3)\ndef decide(kit, params):\n    return []\n"})
        self.assertEqual(report["errors"], 1)
        self.assertTrue(any("did not load" in n for n in report["notes"]))

    def test_the_line_prints_whatever_ends_the_engine(self):
        spec = {"strategy": "quiet", "code": "def decide(kit, params):\n    return []\n", "start": iso(T0), "end": iso(T0 + HOUR)}
        for error in (SystemExit(2), KeyboardInterrupt(), RuntimeError("boom")):
            report = self.run_main(spec, [mock.patch("ltcm.backtest.run_backtest", side_effect=error)])
            self.assertEqual(report["errors"], 1)
            self.assertTrue(any(type(error).__name__ in n for n in report["notes"]), report["notes"])


class BudgetTests(unittest.TestCase):
    """Finding 7: the time budget was checked only between steps, and verbose did not reach History."""

    def test_the_budget_stops_loading_and_the_report_says_nothing_was_replayed(self):
        clock = [1000.0]
        history = FakeHistory(*bucket_events(3, 3, winner_volume=10))
        listing = history.kalshi_settled

        def slow(*args, **kwargs):
            clock[0] += 60.0
            return listing(*args, **kwargs)

        history.kalshi_settled = slow
        with mock.patch("ltcm.backtest._monotonic", lambda: clock[0]):
            report = run_backtest({"strategy": "buckets", "code": BUY_EVERY_BUCKET, "series": ["KXBUCK"], "start": iso(T0),
                                   "end": iso(T0 + 5 * 86400), "max_seconds": 150, "verbose": False}, history=history, trusted_code=True)
        self.assertEqual(report["steps"], 0)
        self.assertGreaterEqual(report["errors"], 1)
        self.assertIn("nothing was replayed", report["incomplete"])
        self.assertLessEqual(len([c for c in history.calls if c[0] == "settled"]), 4, "listing stopped at the budget")
        self.assertIn("second run", report["notes"][0])

    def test_candle_loading_stops_at_the_budget(self):
        clock = [1000.0]
        history = FakeHistory(*bucket_events(4, 2, winner_volume=10))
        candles = history.kalshi_candles

        def slow(*args, **kwargs):
            clock[0] += 60.0
            return candles(*args, **kwargs)

        history.kalshi_candles = slow
        data = DataSet(history, T0, T0 + 6 * HOUR, say=lambda text: None, notes=[], deadline=1100.0)
        with mock.patch("ltcm.backtest._monotonic", lambda: clock[0]):
            data.load_kalshi(series=["KXBUCK"], board=False, max_markets=3000, max_pages=20)
        self.assertIn("candles", data.cut)
        self.assertEqual(len([c for c in history.calls if c[0] == "candles"]), 2)

    def test_history_gives_up_at_its_deadline_instead_of_sleeping_past_it(self):
        transport = Transport([(429, {})] * 5)
        sleeps = []
        history = History(transport, min_interval=0, sleep=sleeps.append, verbose=False, deadline=time.monotonic() + 0.5)
        with self.assertRaises(HistoryTimeout):
            history.kalshi_settled("KXA", start_ts=T0, end_ts=T0 + HOUR)
        self.assertEqual(len(transport.urls), 1)
        self.assertEqual(sleeps, [], "a one-second backoff would pass the deadline")
        history.deadline = time.monotonic() - 1
        with self.assertRaises(HistoryTimeout):
            history.kalshi_settled("KXA", start_ts=T0, end_ts=T0 + HOUR)
        self.assertEqual(len(transport.urls), 1, "no request starts after the deadline")

    def test_quiet_and_compact_runs_silence_history_and_a_sandbox_run_has_a_budget(self):
        made = []

        class Recording(FakeHistory):
            def __init__(self, **kwargs):
                super().__init__()
                made.append(kwargs)
                self.verbose = kwargs.get("verbose", True)
                self.deadline = None

        spec = {"strategy": "quiet", "code": "def decide(kit, params):\n    print('noise')\n    return []\n", "start": iso(T0), "end": iso(T0 + HOUR)}
        quiet, compact = io.StringIO(), io.StringIO()
        with mock.patch("ltcm.history.History", Recording), mock.patch("ltcm.backtest.in_sandbox", lambda: True):
            with contextlib.redirect_stderr(quiet):
                run_backtest({**spec, "verbose": False})
            with contextlib.redirect_stderr(compact):
                run_backtest({**spec, "compact": True})
        self.assertEqual([m["verbose"] for m in made], [False, False])
        self.assertEqual(quiet.getvalue(), "noise\n" * 5, "without compact the strategy's prints still reach stderr")
        self.assertEqual(compact.getvalue(), "", "a compact run prints nothing but its result line")
        passed = Recording()
        with mock.patch("ltcm.backtest.in_sandbox", lambda: True), contextlib.redirect_stderr(io.StringIO()):
            run_backtest({**spec, "verbose": False}, history=passed)
        self.assertIsNotNone(passed.deadline, "540 seconds by default in a sandbox")
        self.assertFalse(passed.verbose)


class SharedCacheTests(unittest.TestCase):
    """Finding 8: each DiskCache counted only its own writes."""

    def test_caches_sharing_a_directory_hold_one_cap_between_them(self):
        import os

        with tempfile.TemporaryDirectory() as tmp:
            cap = 1_000_000
            caches = [DiskCache(tmp, cap) for _ in range(4)]
            peak = 0
            for i in range(9):
                for n, cache in enumerate(caches):
                    cache.put(f"k{n}-{i}", os.urandom(110_000))
                    peak = max(peak, sum(p.stat().st_size for p in Path(tmp).glob("*.z")))
            self.assertLessEqual(peak, cap)
            self.assertIsNotNone(caches[0].get("k3-8"), "the newest entry of another writer survives")
            later = DiskCache(tmp, cap)
            later.put("fresh", os.urandom(110_000))
            self.assertLessEqual(sum(p.stat().st_size for p in Path(tmp).glob("*.z")), cap)


class CompactSplitTests(unittest.TestCase):
    """Finding 9: split_report on a compact line returned two empty halves."""

    def test_a_compact_report_splits_from_its_precomputed_split(self):
        report = {"trade_pnls": [1.0, 2.0, -0.5, 3.0], "trade_notionals": [5.0] * 4, "seed": 7}
        report["split"] = split_report(report)
        report["split_fraction"] = 0.66
        compact = {k: v for k, v in report.items() if k not in ("trade_pnls", "trade_notionals")}
        self.assertEqual(split_report(compact), report["split"])
        self.assertEqual(split_report(compact)["in_sample"]["trades"], 3)
        with self.assertRaises(ValueError):
            split_report(compact, fraction=0.5)


if __name__ == "__main__":
    unittest.main()


class FuturesSimulatorTests(unittest.TestCase):
    """leap: futures -- CDE contracts in the simulator: whole contracts, a multiplier, shorts,
    per-contract fees, exits on the right side (Sept 17, 2026)."""

    def setUp(self):
        self.start = T0
        self.end = T0 + 6 * HOUR
        bars = coinbase_series(T0 - 30 * HOUR, 36 * 12, 300, base=2400.0)  # a 2,400-dollar underlying
        # After T0 + 1h the price falls 2% and stays there.
        for bar in bars:
            if bar["ts"] >= T0 + HOUR:
                for k in ("open", "high", "low", "close"):
                    bar[k] = bar[k] * 0.98
        self.history = FakeHistory(coinbase={("ETP-20DEC30-CDE", "FIVE_MINUTE"): bars})
        self.data = DataSet(self.history, self.start, self.end, say=lambda text: None, notes=[])
        self.sim = simulator(self.data)

    def intent(self, side, price, quantity, **extra):
        return {"instrument": {"asset_class": "future", "symbol": "ETP-20DEC30-CDE", "venue": "coinbase"}, "side": side, "quantity": str(quantity), "order_type": "limit", "limit_price": str(price), **extra}

    def test_a_short_opens_without_a_holding_and_covers_with_the_contract_fee(self):
        self.assertEqual(self.sim.submit(self.intent("sell", 2300, 1), T0), "filled", "a marketable sell opens a short")
        position = self.sim.positions[("future", "ETP-20DEC30-CDE", "")]
        self.assertEqual(position["quantity"], -1)
        self.assertAlmostEqual(position["mult"], 0.1)
        self.assertAlmostEqual(self.sim.fills[-1]["fee"], 0.23, msg="a contract fee, not a percentage")
        ctx = self.sim.context(T0 + MINUTE)
        self.assertEqual(ctx["positions"][0]["quantity"], "-1")
        self.assertAlmostEqual(float(ctx["positions"][0]["average_cost"]), 2400.0 * 0.9999, places=2)
        self.assertEqual(self.sim.submit(self.intent("sell", 2300, 0.5), T0 + MINUTE), "rejected:under one contract")
        # Cover after the 2% fall: a buy at the ask closes the short at a profit of ~48 x 0.1 less two fees.
        self.assertEqual(self.sim.submit(self.intent("buy", 2500, 1), T0 + 2 * HOUR), "filled")
        self.assertEqual(len(self.sim.closed), 1)
        closed = self.sim.closed[0]
        self.assertEqual((closed["asset_class"], closed["how"]), ("future", "covered"))
        self.assertAlmostEqual(closed["pnl"], (2400 * 0.9999 - 2400 * 0.98 * 1.0001) * 0.1 - 0.46, places=3)

    def test_a_shorts_stop_and_target_sit_on_the_right_side_and_a_buy_never_flips(self):
        self.assertEqual(self.sim.submit(self.intent("sell", 2300, 2, stop_price="2500", target_price="2360", holding_period_hours=5), T0), "filled")
        self.sim.advance(T0 + 30 * MINUTE)
        self.assertEqual(self.sim.closed, [], "no move yet")
        self.sim.advance(T0 + HOUR + 10 * MINUTE)
        self.assertEqual(len(self.sim.closed), 1, "the 2% fall reached the target; a short's target is below entry")
        self.assertEqual(self.sim.closed[0]["how"], "covered")
        self.assertGreater(self.sim.closed[0]["pnl"], 0)
        # Long 1 then a sell of 3: the reducing order is capped at the holding, never a flip.
        self.assertEqual(self.sim.submit(self.intent("buy", 2500, 1), T0 + 2 * HOUR), "filled")
        self.assertEqual(self.sim.submit(self.intent("sell", 2200, 3), T0 + 2 * HOUR + MINUTE), "filled")
        self.assertNotIn(("future", "ETP-20DEC30-CDE", ""), self.sim.positions)
        self.assertEqual(self.sim.closed[-1]["how"], "sold")

    def test_the_kit_lists_perps_from_history_and_quotes_them(self):
        kit = BacktestKit(self.data, self.sim, T0 + 7 * MINUTE, products=None, half_spread=0.0001)
        rows = kit.futures()
        self.assertEqual([r["symbol"] for r in rows], ["ETP-20DEC30-CDE"], "only contracts with history")
        self.assertEqual((rows[0]["contract_size"], rows[0]["perpetual"]), (0.1, True))
        self.assertAlmostEqual(rows[0]["contract_usd"], 240.0, delta=1.0)
        quote = kit.quote("ETP-20DEC30-CDE", "future")
        self.assertEqual(quote["instrument"]["asset_class"], "future")
        self.assertEqual(len(kit.bars("ETP-20DEC30-CDE", "5m", 3, "future")), 3)
        self.assertEqual(self.sim.submit({**self.intent("sell", 2300, 1), "instrument": {"asset_class": "future", "symbol": "XYZ-20DEC30-CDE"}}, T0), "rejected:futures contract not in the simulator's table")
