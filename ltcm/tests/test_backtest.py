"""Backtests: history as of a moment, a conservative book, and the report contract. No network."""

from __future__ import annotations

import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ltcm.backtest import (
    RESULT_PREFIX,
    BacktestKit,
    DataSet,
    Simulator,
    bootstrap_ci,
    iso,
    kalshi_plan,
    kalshi_taker_fee,
    main,
    max_drawdown,
    parse_time,
    run_backtest,
    split_report,
)
from ltcm.history import DiskCache, History

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
    data.load_kalshi(series=list(series), board=False, max_markets=3000, min_volume=None, max_pages=20)
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
        self.assertAlmostEqual(fill["fee"], kalshi_taker_fee(0.55) * 5)
        self.assertAlmostEqual(kalshi_taker_fee(0.55), 0.02)
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
        self.assertAlmostEqual(sim.closed[0]["pnl"], 10 * (1.0 - 0.55) - 10 * kalshi_taker_fee(0.55))
        self.assertEqual(sim.closed[0]["ts"], self.open + HOUR)

    def test_resting_orders_expire_at_close(self):
        sim = self.build([candle(self.open + MINUTE, 0.40, 0.45)])
        sim.submit(buy(self.ticker, "yes", 0.20, 2), self.open + 2 * MINUTE)
        sim.advance(self.open + HOUR)
        self.assertEqual(sim.orders, {})
        self.assertEqual(sim.counts["expired"], 1)

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
        report = run_backtest({"strategy": "custom", "code": code, "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR)}, history=FakeHistory())
        self.assertIn("NWS", report["unsupported"], "a strategy that swallows the error is still unsupported")

    def test_strategy_errors_are_counted_never_fatal(self):
        code = "def decide(kit, params):\n    raise RuntimeError('boom')\n"
        report = run_backtest({"strategy": "broken", "code": code, "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR), "step_minutes": 15}, history=FakeHistory())
        self.assertEqual(report["steps"], 5)
        self.assertEqual(report["errors"], 5)
        self.assertTrue(any("boom" in n for n in report["notes"]))
        report = run_backtest({"strategy": "bad", "code": "def decide(:\n", "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR)}, history=FakeHistory())
        self.assertEqual(report["errors"], 1)
        self.assertEqual(report["steps"], 0)

    def test_a_strategy_printing_does_not_touch_stdout(self):
        code = "def decide(kit, params):\n    print('chatty')\n    return []\n"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            run_backtest({"strategy": "chatty", "code": code, "verbose": False, "start": iso(T0), "end": iso(T0 + HOUR)}, history=FakeHistory())
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
                mock.patch("ltcm.history.History", lambda **kwargs: FakeHistory()):
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


if __name__ == "__main__":
    unittest.main()
