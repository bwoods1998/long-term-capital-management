import contextlib
import io
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from league import replay
from league.replay import kalshi_taker_fee, parse_result, run_replay

REPLAY_FILE = Path(replay.__file__).resolve()
REPO = REPLAY_FILE.parent.parent
BTC = "BTC/USD"
MKT = "KXBTCD-26SEP1014-T80999.99"
WIDE = {"max_position_usd": 1e9, "max_order_usd": 1e9}


# ------------------------------------------------------------------------------------ fixtures
def t_at(minutes, base=datetime(2026, 9, 10, 13, 0, tzinfo=timezone.utc)):
    return (base + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def bar(c, l=None, h=None):
    return {"o": c, "h": c if h is None else h, "l": c if l is None else l, "c": c, "v": 10.0}


def alpaca_tape(bars, *, symbol=BTC, horizon="hour", minutes=5, half_spread_bps=0.0):
    """One symbol, one bar a step; a number is a flat bar at that close and None is a missing bar."""
    steps = []
    for i, b in enumerate(bars):
        b = bar(b) if isinstance(b, (int, float)) else b
        steps.append({"t": t_at(i * minutes), "bars": {} if b is None else {symbol: b}})
    return {"venue": "alpaca", "horizon": horizon, "step_seconds": minutes * 60,
            "half_spread_bps": half_spread_bps, "steps": steps}


def market(yes_bid, yes_ask, *, ticker=MKT, close=15, series="KXBTCD", **more):
    return {"market": ticker, "series": series, "title": "BTC above 81k?", "yes_bid": yes_bid, "yes_ask": yes_ask,
            "close_time": t_at(close), "volume_24h": 12000, "open_interest": 3400, "strike": 80999.99, **more}


def kalshi_tape(rows_by_step, results, *, minutes=5, horizon="hour"):
    steps = [{"t": t_at(i * minutes), "markets": rows} for i, rows in enumerate(rows_by_step)]
    return {"venue": "kalshi", "horizon": horizon, "step_seconds": minutes * 60, "steps": steps, "results": results}


def script(venue="alpaca", symbols=(BTC,), limit=120):
    """A strategy that plays `params["plan"]` ({"<step index>": [intents]}), cancels everything at
    the steps in `params["cancel_at"]`, and logs what it was shown into its memory."""
    return '''
NEEDS = {"venue": "__VENUE__", "horizon": "hour", "style": "scripted", "symbols": __SYMBOLS__,
         "bars": {"timeframe": "5Min", "limit": __LIMIT__}}
PARAMS = {"plan": {}, "cancel_at": []}


def decide(ctx):
    memory = ctx["memory"]
    i = memory.get("i", 0)
    log = memory.get("log", [])
    bars = {s: [len(b), b[-1]["t"] if b else None, b[-1]["c"] if b else None] for s, b in ctx.get("bars", {}).items()}
    log.append({"now": ctx["now"], "cash": ctx["cash"], "equity": ctx["equity"], "bars": bars,
                "quotes": ctx.get("quotes"), "positions": ctx["positions"], "open_orders": ctx["open_orders"]})
    cancels = [o["order_id"] for o in ctx["open_orders"]] if i in ctx["params"]["cancel_at"] else []
    return {"intents": ctx["params"]["plan"].get(str(i), []), "cancels": cancels, "thought": "scripted",
            "memory": {"i": i + 1, "log": log}}
'''.replace("__VENUE__", venue).replace("__SYMBOLS__", json.dumps(list(symbols))).replace("__LIMIT__", str(limit))


def buy(notional=None, *, quantity=None, symbol=BTC, **more):
    size = {"quantity": quantity} if quantity is not None else {"notional_usd": notional}
    return {"symbol": symbol, "side": "buy", "type": "market", "reason": "test", **size, **more}


def sell(quantity, *, symbol=BTC, **more):
    return {"symbol": symbol, "side": "sell", "type": "market", "quantity": quantity, "reason": "test", **more}


def limit(side, quantity, price, *, symbol=BTC, **more):
    return {"symbol": symbol, "side": side, "type": "limit", "quantity": quantity, "limit_price": price,
            "reason": "test", **more}


def event(side, quantity, *, leg="yes", price=None, ticker=MKT, **more):
    kind = {"type": "market"} if price is None else {"type": "limit", "limit_price": price}
    return {"market": ticker, "leg": leg, "side": side, "quantity": quantity, "reason": "test", **kind, **more}


def play(plan, tape, *, code=None, cancel_at=(), **kw):
    code = code or script(tape["venue"])
    result = run_replay(code, {"plan": {str(k): v for k, v in plan.items()}, "cancel_at": list(cancel_at)},
                        tape, audit=True, **kw)
    assert result["ok"], result
    return result


def log_of(result):
    return result["final_memory"]["log"]


# ------------------------------------------------------------------------------ no look-ahead
class NoLookAheadTest(unittest.TestCase):
    def test_bars_never_run_past_now_and_the_window_is_the_asked_limit(self):
        tape = alpaca_tape([100 + i for i in range(8)])
        result = play({}, tape, code=script(limit=3))
        self.assertEqual(result["errors"], 0)
        for i, seen in enumerate(log_of(result)):
            count, last_t, last_close = seen["bars"][BTC]
            self.assertEqual(seen["now"], tape["steps"][i]["t"])
            self.assertEqual(last_t, seen["now"])  # the newest bar shown is the one that closed now
            self.assertEqual(last_close, 100 + i)
            self.assertEqual(count, min(i + 1, 3))

    def test_a_strategy_that_checks_every_bar_itself_finds_nothing_from_the_future(self):
        code = '''
NEEDS = {"venue": "alpaca", "symbols": ["BTC/USD"], "bars": {"limit": 500}}
PARAMS = {}
def decide(ctx):
    for series in ctx["bars"].values():
        if any(b["t"] > ctx["now"] for b in series) or series[-1]["t"] != ctx["now"]:
            raise ValueError("saw the future")
        if [b["t"] for b in series] != sorted(b["t"] for b in series):
            raise ValueError("not oldest first")
    return {"intents": [], "memory": {}}
'''
        result = run_replay(code, None, alpaca_tape([100, 101, 102, 103, 104, 105]))
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["steps"], 6)

    def test_market_order_before_a_jump_pays_the_price_before_the_jump(self):
        tape = alpaca_tape([100, 100, 100, 200, 200], half_spread_bps=2.0)
        result = play({2: [buy(50)]}, tape)
        (fill,) = result["fill_log"]
        self.assertEqual(fill["t"], t_at(10))
        self.assertAlmostEqual(fill["price"], 100 * 1.0002, places=9)  # step 2's ask, not step 3's
        self.assertEqual(fill["liquidity"], "taker")
        quantity = fill["quantity"]
        self.assertAlmostEqual(quantity, math.floor(50 / 100.02 * 1e9) / 1e9, places=12)
        cash = 200 - quantity * 100.02 * 1.0025
        self.assertAlmostEqual(result["final_equity"], cash + quantity * 200 * (1 - 0.0002), places=6)

    def test_what_was_shown_does_not_depend_on_what_comes_later(self):
        plan = {1: [buy(40)], 2: [limit("sell", 0.1, 104)]}
        calm = play(plan, alpaca_tape([100, 101, 102, 103, 103, 103], half_spread_bps=2.0))
        wild = play(plan, alpaca_tape([100, 101, 102, 103, 500, 5], half_spread_bps=2.0))
        self.assertEqual(log_of(calm)[:4], log_of(wild)[:4])
        self.assertNotEqual(log_of(calm)[4:], log_of(wild)[4:])

    def test_a_resting_order_cannot_fill_on_the_step_it_was_placed(self):
        # Step 0's own bar traded down to 90, but the order did not exist yet.
        tape = alpaca_tape([bar(100, l=90), 100, 100])
        result = play({0: [limit("buy", 0.5, 95)]}, tape)
        self.assertEqual(result["fills"], 0)
        self.assertEqual(result["open_orders"], 1)
        self.assertEqual(result["final_equity"], 200.0)


# ------------------------------------------------------------------------------- alpaca fills
class DatedQuotesTest(unittest.TestCase):
    def test_a_replay_quote_carries_its_decision_time_like_a_live_quote(self):
        """Sept 22, 2026: strategies that refuse undated quotes never traded in replay."""
        code = '''
NEEDS = {"venue": "alpaca", "symbols": ["BTC/USD"], "bars": {"limit": 5}}
PARAMS = {}
def decide(ctx):
    for quote in ctx["quotes"].values():
        if quote.get("t") != ctx["now"]:
            raise ValueError("an undated or stale replay quote")
    held = [p for p in ctx["positions"] if p["symbol"] == "BTC/USD"]
    side = "sell" if held else "buy"
    size = {"quantity": held[0]["quantity"]} if held else {"notional_usd": 50.0}
    return {"intents": [{"symbol": "BTC/USD", "side": side, "type": "market", "reason": "dated", **size}], "memory": {}}
'''
        result = run_replay(code, None, alpaca_tape([100, 101, 102, 103, 104, 105]))
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], 0)
        self.assertGreater(result["trades"], 0)


class AlpacaFillTest(unittest.TestCase):
    def test_resting_buy_is_not_filled_by_a_touch(self):
        result = play({0: [limit("buy", 0.5, 99)]}, alpaca_tape([100, bar(100, l=99), bar(100, l=99)]))
        self.assertEqual(result["fills"], 0)
        self.assertEqual(result["open_orders"], 1)
        order = log_of(result)[1]["open_orders"][0]
        self.assertEqual((order["order_id"], order["symbol"], order["side"], order["quantity"], order["limit_price"],
                          order["filled"], order["submitted_at"]), ("ord-000001", BTC, "buy", 0.5, 99.0, 0.0, t_at(0)))

    def test_resting_buy_fills_through_at_its_own_price_with_the_maker_fee(self):
        result = play({0: [limit("buy", 0.5, 99)]}, alpaca_tape([100, bar(100, l=99), bar(100, l=98.99), 100]))
        (fill,) = result["fill_log"]
        self.assertEqual((fill["t"], fill["price"], fill["liquidity"], fill["quantity"]), (t_at(10), 99.0, "maker", 0.5))
        self.assertAlmostEqual(fill["fee"], 0.5 * 99 * 0.0015, places=12)
        self.assertEqual((result["fills"], result["maker_fills"], result["open_orders"]), (1, 1, 0))
        self.assertAlmostEqual(result["final_equity"], 200 - 49.5 - 0.07425 + 0.5 * 100, places=9)
        position = log_of(result)[2]["positions"][0]  # shown to the strategy on the step it filled
        self.assertEqual((position["symbol"], position["quantity"], position["average_cost"]), (BTC, 0.5, 99.0))

    def test_resting_sell_needs_a_high_strictly_above(self):
        plan = {0: [buy(quantity=0.5)], 1: [limit("sell", 0.5, 105)]}
        touched = play(plan, alpaca_tape([100, 100, bar(100, h=105), 100]))
        self.assertEqual(touched["fills"], 1)
        through = play(plan, alpaca_tape([100, 100, bar(100, h=105.01), 100]))
        self.assertEqual((through["fills"], through["maker_fills"], through["trades"]), (2, 1, 1))
        self.assertEqual(through["fill_log"][1]["price"], 105.0)
        fees = 50 * 0.0025 + 52.5 * 0.0015
        self.assertAlmostEqual(through["final_equity"], 200 + 2.5 - fees, places=9)
        self.assertAlmostEqual(through["trade_returns"][0], (2.5 - fees) / 200, places=9)

    def test_crossing_limit_fills_at_the_touch_as_a_taker(self):
        result = play({0: [limit("buy", 0.5, 101)]}, alpaca_tape([100, 100], half_spread_bps=2.0))
        (fill,) = result["fill_log"]
        self.assertAlmostEqual(fill["price"], 100.02, places=9)  # the ask, not the 101 it was willing to pay
        self.assertEqual(fill["liquidity"], "taker")
        self.assertEqual(result["maker_fills"], 0)

    def test_post_only_that_would_cross_is_refused_and_one_that_would_not_rests(self):
        result = play({0: [limit("buy", 0.5, 101, post_only=True), limit("buy", 0.2, 99, post_only=True)]},
                      alpaca_tape([100, 100]))
        self.assertEqual((result["fills"], result["refused"], result["open_orders"]), (0, 1, 1))
        self.assertIn("post_only order would cross the touch", result["refusal_reasons"])

    def test_crypto_taker_round_trip_fees_are_exact(self):
        result = play({0: [buy(quantity=0.5)], 2: [sell(0.5)]}, alpaca_tape([100, 100, 110]))
        self.assertAlmostEqual(result["fees_usd"], 50 * 0.0025 + 55 * 0.0025, places=12)
        self.assertAlmostEqual(result["final_equity"], 200 - 50 - 0.125 + 55 - 0.1375, places=9)
        self.assertEqual(result["trades"], 1)
        self.assertAlmostEqual(result["trade_returns"][0], 4.7375 / 200, places=12)
        self.assertAlmostEqual(result["return_pct"], 4.7375 / 200 * 100, places=9)

    def test_equities_pay_no_fee_and_are_marked_at_the_bid(self):
        tape = alpaca_tape([650, 650], symbol="SPY", half_spread_bps=1.0)
        result = play({0: [buy(quantity=0.1, symbol="SPY")]}, tape, code=script(symbols=("SPY",)))
        self.assertEqual(result["fees_usd"], 0.0)
        self.assertAlmostEqual(result["final_equity"], 200 - 0.1 * 650 * 0.0002, places=9)  # the spread only

    def test_missing_bar_means_no_fill_no_order_and_the_last_mark(self):
        tape = alpaca_tape([100, None, bar(90, l=80)])
        result = play({0: [buy(quantity=0.5), limit("buy", 0.2, 95)], 1: [buy(10)]}, tape)
        log = log_of(result)
        self.assertEqual(log[1]["bars"][BTC], [1, t_at(0), 100])  # history kept, nothing invented
        self.assertEqual(log[1]["quotes"], {})
        self.assertAlmostEqual(log[1]["equity"], 200 - 0.125, places=9)  # marked where it last traded
        self.assertEqual(len(log[1]["open_orders"]), 1)
        self.assertEqual(result["refusal_reasons"], {"no quote for this instrument at this step": 1})
        self.assertEqual([f["t"] for f in result["fill_log"]], [t_at(0), t_at(10)])
        self.assertEqual(log[2]["bars"][BTC], [2, t_at(10), 90])


# ------------------------------------------------------------------------------ the House's rules
class RulesTest(unittest.TestCase):
    def test_no_shorts(self):
        tape = alpaca_tape([100, 100, 100, 100])
        plan = {0: [sell(0.1)], 1: [buy(quantity=0.5)], 2: [sell(0.6), limit("sell", 0.4, 120), sell(0.2)], 3: [sell(0.1)]}
        result = play(plan, tape)
        # Refused: the naked sell, the oversell, and 0.2 when 0.4 of the 0.5 is already offered.
        self.assertEqual(result["refused"], 3)
        self.assertEqual(set(result["refusal_reasons"]), {"no shorts: a sell is limited to what is held and not already offered"})
        self.assertEqual(result["fills"], 2)
        self.assertAlmostEqual(log_of(result)[3]["positions"][0]["quantity"], 0.5)
        self.assertEqual(result["open_positions"], 1)

    def test_no_leverage_counts_the_fee_and_cash_behind_resting_buys(self):
        tape = alpaca_tape([100, 100, 100, 100])
        result = play({0: [buy(100)]}, tape, stake=100.0, limits=WIDE)
        self.assertEqual((result["fills"], result["refused"]), (0, 1))  # $100 + the fee is more than $100
        plan = {0: [limit("buy", 0.6, 99)], 1: [buy(50)], 3: [buy(50)]}
        result = play(plan, tape, stake=100.0, limits=WIDE, cancel_at=[2])
        self.assertEqual(result["refusal_reasons"], {"no leverage: not enough free cash for the order and its fee": 1})
        self.assertEqual([f["t"] for f in result["fill_log"]], [t_at(15)])  # only after the cancel freed the cash
        self.assertEqual(result["open_orders"], 0)

    def test_order_cap_and_position_cap(self):
        tape = alpaca_tape([100, 100, 100, 100, 100])
        plan = {0: [buy(80)], 1: [buy(75)], 2: [buy(30)], 3: [buy(20), limit("buy", 0.12, 90)], 4: [limit("buy", 0.12, 90)]}
        result = play(plan, tape, stake=500.0, limits={"max_position_usd": 100.0, "max_order_usd": 75.0})
        self.assertEqual(result["refusal_reasons"], {"over the order cap": 1, "over the position cap": 2})
        self.assertEqual([round(f["quantity"] * f["price"], 6) for f in result["fill_log"]], [75.0, 20.0])
        # A resting bid counts toward the position: 0.95 held at its 90 + 10.8 working + 10.8 is over 100.
        self.assertEqual(result["open_orders"], 1)

    def test_a_sell_is_not_held_to_the_buy_caps(self):
        tape = alpaca_tape([100, 100, 300])
        result = play({0: [buy(quantity=0.5)], 2: [sell(0.5)]}, tape, limits={"max_position_usd": 100.0, "max_order_usd": 75.0})
        self.assertEqual((result["fills"], result["refused"]), (2, 0))  # closing $150 of holdings is allowed

    def test_an_alpaca_crypto_buy_asked_under_ten_dollars_never_fills(self):
        # Alpaca refuses a crypto order under $10 and the House refuses the buy before it is sent
        # (Sept 22, 2026). As in the House it is the dollars ASKED that count: $10 floored to the
        # step fills; a limit sized in units counts at its limit, not at the touch it fills at.
        tape = alpaca_tape([81000, 81000, 81000, 81000, 81000])
        plan = {0: [buy(9.99)], 1: [buy(10)], 2: [limit("buy", 0.0001, 81500)], 3: [limit("buy", 0.000123, 82000)]}
        result = play(plan, tape)
        self.assertEqual(result["refusal_reasons"], {"alpaca refuses a crypto buy under $10": 2})
        self.assertEqual([f["t"] for f in result["fill_log"]], [t_at(5), t_at(15)])
        self.assertAlmostEqual(result["fill_log"][1]["quantity"] * result["fill_log"][1]["price"], 9.963, places=9)

    def test_sells_and_stocks_are_not_held_to_the_crypto_minimum(self):
        result = play({0: [buy(20)], 1: [sell(0.0001)]}, alpaca_tape([81000, 81000, 81000]))
        self.assertEqual((result["fills"], result["refused"]), (2, 0))  # an $8.10 exit trims the holding
        spy = alpaca_tape([650, 650], symbol="SPY")
        result = play({0: [buy(5, symbol="SPY")]}, spy, code=script(symbols=("SPY",)))
        self.assertEqual((result["fills"], result["refused"]), (1, 0))

    def test_notional_rounds_down_to_the_step(self):
        result = play({0: [buy(20)]}, alpaca_tape([81000, 81000]))
        self.assertEqual(result["fill_log"][0]["quantity"], 0.000246913)  # 20 / 81000 = 0.00024691358...
        spy = alpaca_tape([650, 650], symbol="SPY")
        plan = {0: [{"symbol": "SPY", "side": "buy", "type": "limit", "limit_price": 651, "notional_usd": 2000, "reason": "t"},
                    buy(2000, symbol="SPY")]}
        result = play(plan, spy, code=script(symbols=("SPY",)), stake=10000.0, limits=WIDE)
        self.assertEqual([f["quantity"] for f in result["fill_log"]], [3.0, 3.076923076])  # whole shares on a limit

    def test_malformed_intents_are_refused_and_only_eight_are_taken(self):
        junk = [
            "buy btc", {"symbol": BTC, "side": "hold", "type": "market", "quantity": 1, "reason": "x"},
            {"symbol": BTC, "side": "buy", "type": "market", "quantity": 0.1, "notional_usd": 10, "reason": "both"},
            {"symbol": BTC, "side": "buy", "type": "market", "reason": "no size"},
            {"symbol": BTC, "side": "buy", "type": "limit", "quantity": 0.1, "reason": "no price"},
            {"symbol": BTC, "side": "buy", "type": "market", "quantity": 0.1},  # no reason
            {"symbol": BTC, "side": "buy", "type": "market", "quantity": "0.1", "reason": "a string"},
            {"symbol": "ETH/USD", "side": "buy", "type": "market", "quantity": 0.1, "reason": "not on the tape"},
            buy(10), buy(10),  # the ninth and tenth: over the limit of eight
        ]
        result = play({0: junk}, alpaca_tape([100, 100]))
        self.assertEqual((result["refused"], result["fills"], result["errors"]), (10, 0, 0))
        self.assertEqual(result["refusal_reasons"]["over 8 intents in one decision"], 2)

    def test_cancel_of_an_unknown_order_and_sizes_that_are_not_numbers_are_counted(self):
        code = '''
NEEDS = {"venue": "alpaca"}
PARAMS = {}
def decide(ctx):
    sizes = [float("nan"), float("inf"), -1, True]
    return {"cancels": ["ord-nope", 7],
            "intents": [{"symbol": "BTC/USD", "side": "buy", "type": "market", "quantity": q, "reason": "x"} for q in sizes]}
'''
        result = run_replay(code, None, alpaca_tape([100, 100]))
        self.assertEqual((result["ok"], result["refused"], result["fills"], result["errors"]), (True, 12, 0, 0))


# ------------------------------------------------------------------------------------- kalshi
class KalshiTest(unittest.TestCase):
    def favourite(self, results, closing_rows=()):
        tape = kalshi_tape([[market(0.91, 0.93)], [market(0.91, 0.93)], [market(0.95, 0.97)], list(closing_rows), []], results)
        return play({0: [event("buy", 10)]}, tape)

    def test_taker_fee_is_exact_and_rounded_up(self):
        self.assertEqual(kalshi_taker_fee(10, 0.93), 0.0456)  # 0.045570 -> up
        self.assertEqual(kalshi_taker_fee(100, 0.5), 1.75)  # already on the grid: not bumped by float noise
        self.assertEqual(kalshi_taker_fee(1, 0.5), 0.0175)
        self.assertEqual(kalshi_taker_fee(3, 0.07), kalshi_taker_fee(3, 0.93))

    def test_favourite_that_settles_yes_makes_seven_cents_a_contract_less_the_fee(self):
        result = self.favourite({MKT: "yes"})
        self.assertAlmostEqual(result["final_equity"], 200 + 10 * 0.07 - 0.0456, places=9)
        self.assertEqual((result["trades"], result["fills"], result["unresolved"], result["open_positions"]), (1, 1, 0, 0))
        self.assertAlmostEqual(result["trade_returns"][0], (0.7 - 0.0456) / 200, places=12)
        log = log_of(result)
        position = log[1]["positions"][0]
        self.assertEqual((position["market"], position["leg"], position["quantity"], position["average_cost"], position["mark"]),
                         (MKT, "yes", 10.0, 0.93, 0.91))
        self.assertAlmostEqual(log[1]["equity"], 200 - 9.3 - 0.0456 + 10 * 0.91, places=9)  # held at the bid
        self.assertAlmostEqual(log[3]["cash"], 200.6544, places=9)  # paid at the first step at or after the close
        self.assertEqual(log[3]["positions"], [])

    def test_favourite_that_settles_no_loses_the_ninety_three_cents(self):
        result = self.favourite({MKT: "no"})
        self.assertAlmostEqual(result["final_equity"], 200 - 9.3 - 0.0456, places=9)
        self.assertAlmostEqual(result["trade_returns"][0], -9.3456 / 200, places=12)

    def test_unresolved_market_refunds_the_price_paid(self):
        result = self.favourite({})
        self.assertEqual((result["unresolved"], result["trades"], result["trade_returns"]), (1, 0, []))
        self.assertAlmostEqual(result["final_equity"], 200 - 0.0456, places=9)

    def test_no_leg_resting_buy_fills_through_the_complement(self):
        rows = [[market(0.55, 0.58)],                      # NO ask 0.45: a NO bid of 0.40 rests
                [market(0.56, 0.58, yes_bid_high=0.60)],   # NO ask touched 0.40: not through
                [market(0.56, 0.58, yes_bid_high=0.61)],   # NO ask traded 0.39: through
                []]
        result = play({0: [event("buy", 10, leg="no", price=0.40, post_only=True)]}, kalshi_tape(rows, {MKT: "no"}))
        (fill,) = result["fill_log"]
        self.assertEqual((fill["t"], fill["leg"], fill["price"], fill["fee"], fill["liquidity"]), (t_at(10), "no", 0.40, 0.0, "maker"))
        self.assertEqual(len(log_of(result)[1]["open_orders"]), 1)
        self.assertAlmostEqual(log_of(result)[2]["positions"][0]["mark"], 0.42, places=9)  # NO bid = 1 - YES ask
        self.assertAlmostEqual(result["final_equity"], 200 - 4 + 10, places=9)

    def test_no_leg_resting_sell_fills_through_the_complement(self):
        rows = [[market(0.55, 0.58)],                      # NO ask 0.45, NO bid 0.42
                [market(0.55, 0.58, yes_ask_low=0.50)],    # NO bid touched 0.50: not through
                [market(0.55, 0.58, yes_ask_low=0.49)],    # NO bid traded 0.51: through
                []]
        plan = {0: [event("buy", 10, leg="no"), event("sell", 10, leg="no", price=0.50)]}
        result = play(plan, kalshi_tape(rows, {MKT: "yes"}))
        self.assertEqual([(f["t"], f["price"], f["liquidity"]) for f in result["fill_log"]],
                         [(t_at(0), 0.45, "taker"), (t_at(10), 0.50, "maker")])
        self.assertAlmostEqual(result["final_equity"], 200 - 4.5 - 0.1733 + 5.0, places=9)
        self.assertEqual(result["trades"], 1)

    def test_yes_leg_resting_buy_needs_the_ask_strictly_below(self):
        rows = [[market(0.91, 0.93)], [market(0.91, 0.93, yes_ask_low=0.90)], [market(0.91, 0.93)], []]
        plan = {0: [event("buy", 10, price=0.90)]}
        self.assertEqual(play(plan, kalshi_tape(rows, {MKT: "yes"}))["fills"], 0)
        rows[1] = [market(0.91, 0.93, yes_ask_low=0.89)]
        result = play(plan, kalshi_tape(rows, {MKT: "yes"}))
        self.assertEqual((result["fills"], result["maker_fills"], result["fees_usd"]), (1, 1, 0.0))
        self.assertAlmostEqual(result["final_equity"], 201.0, places=9)

    def test_buys_under_fifteen_cents_are_refused(self):
        rows = [[market(0.08, 0.10, ticker="LONGSHOT"), market(0.90, 0.92, ticker="FAV"), market(0.50, 0.52, ticker="COIN")]]
        plan = {0: [event("buy", 10, ticker="LONGSHOT"), event("buy", 10, leg="no", ticker="FAV"),
                    event("buy", 10, price=0.14, ticker="COIN"), event("buy", 10, price=0.15, ticker="COIN")]}
        result = play(plan, kalshi_tape(rows + rows, {}))
        self.assertEqual(result["refusal_reasons"], {"kalshi buys under $0.15 are refused": 3})
        self.assertEqual((result["fills"], result["open_orders"]), (0, 1))

    def test_resting_order_dies_when_its_market_closes(self):
        other = market(0.50, 0.52, ticker="LATER", close=600)
        rows = [[market(0.91, 0.93, close=10), other], [market(0.91, 0.93, close=10), other], [other], [other]]
        # $10 of stake, $8 of it behind the resting bid: the $5.20 buy fits only once that bid is gone.
        plan = {0: [event("buy", 10, price=0.80)], 1: [event("buy", 10, ticker="LATER")], 2: [event("buy", 10, ticker="LATER")]}
        result = play(plan, kalshi_tape(rows, {MKT: "yes"}), stake=10.0)
        log = log_of(result)
        self.assertEqual(len(log[1]["open_orders"]), 1)
        self.assertEqual(log[2]["open_orders"], [])  # the market closed at step 2 and is not on the tape any more
        self.assertEqual((result["expired_orders"], result["open_orders"]), (1, 0))
        self.assertEqual(result["refusal_reasons"], {"no leverage: not enough free cash for the order and its fee": 1})
        self.assertEqual([(f["t"], f["market"]) for f in result["fill_log"]], [(t_at(10), "LATER")])

    def test_a_bid_left_resting_into_the_close_is_picked_off_if_the_tape_shows_it(self):
        rows = [[market(0.91, 0.93, close=10)], [market(0.91, 0.93, close=10)],
                [market(0.02, 0.05, close=10, yes_ask_low=0.05)]]  # the closing step: the market collapsed
        result = play({0: [event("buy", 10, price=0.80)]}, kalshi_tape(rows, {MKT: "no"}))
        self.assertEqual((result["fills"], result["trades"]), (1, 1))
        self.assertAlmostEqual(result["final_equity"], 192.0, places=9)

    def test_whole_contracts_only(self):
        rows = [[market(0.91, 0.93)], [market(0.91, 0.93)]]
        plan = {0: [{"market": MKT, "leg": "yes", "side": "buy", "type": "market", "notional_usd": 10, "reason": "t"},
                    event("buy", 2.9), event("buy", 0.5)]}
        result = play(plan, kalshi_tape(rows, {}))
        self.assertEqual([f["quantity"] for f in result["fill_log"]], [10.0, 2.0])  # $10 / 0.93 = 10.75 -> 10
        self.assertEqual(result["refusal_reasons"], {"the size rounds down to nothing at this instrument's step": 1})

    def test_prices_outside_zero_to_one_and_closed_or_unknown_markets_are_refused(self):
        rows = [[market(0.50, 0.52), market(0.50, 0.52, ticker="SHUT", close=0)]]
        plan = {0: [event("buy", 5, price=1.0), event("buy", 5, price=0), event("buy", 5, price=-0.2),
                    event("buy", 5, ticker="SHUT"), event("buy", 5, ticker="NOPE"), event("buy", 5, leg="maybe")]}
        result = play(plan, kalshi_tape(rows + rows, {}))
        self.assertEqual((result["refused"], result["fills"], result["open_orders"]), (6, 0, 0))

    def test_sell_before_the_close_takes_the_bid(self):
        rows = [[market(0.50, 0.52)], [market(0.60, 0.62)], []]
        result = play({0: [event("buy", 10)], 1: [event("sell", 10)]}, kalshi_tape(rows, {MKT: "yes"}))
        fees = kalshi_taker_fee(10, 0.52) + kalshi_taker_fee(10, 0.60)
        self.assertAlmostEqual(result["final_equity"], 200 + 10 * (0.60 - 0.52) - fees, places=9)
        self.assertEqual((result["trades"], result["open_positions"]), (1, 0))

    def test_ctx_shows_only_the_asked_open_markets_and_nothing_about_the_outcome(self):
        code = '''
import json
NEEDS = {"venue": "kalshi", "horizon": "hour", "series": ["KXBTCD"], "max_hours_to_close": 1}
PARAMS = {}
def decide(ctx):
    text = json.dumps(ctx)
    return {"intents": [], "memory": {"tickers": [m["market"] for m in ctx["markets"]],
                                      "fields": sorted(ctx["markets"][0]), "hours": ctx["markets"][0]["hours_to_close"],
                                      "leak": ("results" in text) or ("yes_ask_low" in text) or ("SECRET" in text)}}
'''
        rows = [[market(0.91, 0.93, ticker="SOON", close=30, yes_ask_low=0.90, yes_bid_high=0.95),
                 market(0.50, 0.52, ticker="ETH", close=30, series="KXETHD"),
                 market(0.50, 0.52, ticker="FAR", close=180),
                 market(0.50, 0.52, ticker="SHUT", close=0)]]
        tape = kalshi_tape(rows, {"SOON": "yes", "SECRET": "no"})
        result = run_replay(code, None, tape, audit=True)
        memory = result["final_memory"]
        self.assertEqual(memory["tickers"], ["SOON"])
        self.assertEqual(memory["hours"], 0.5)
        self.assertEqual(memory["fields"], sorted(["market", "series", "title", "yes_bid", "yes_ask", "close_time",
                                                   "hours_to_close", "volume_24h", "open_interest", "strike"]))
        self.assertFalse(memory["leak"])


# ------------------------------------------------------------------------------------- blocks
class BlocksTest(unittest.TestCase):
    def test_hour_blocks_active_flags_and_growth_that_adds_up(self):
        tape = alpaca_tape([100, 100, 100, 110, 110, 110], minutes=30)
        result = play({2: [buy(quantity=0.5)], 3: [sell(0.5)]}, tape)
        self.assertEqual([b["key"] for b in result["blocks"]], ["2026-09-10T13", "2026-09-10T14", "2026-09-10T15"])
        self.assertEqual([b["active"] for b in result["blocks"]], [False, True, False])
        self.assertEqual([result["blocks"][0]["log_growth"], result["blocks"][2]["log_growth"]], [0.0, 0.0])
        self.assertAlmostEqual(sum(b["log_growth"] for b in result["blocks"]), math.log(result["final_equity"] / 200), places=9)
        self.assertAlmostEqual(result["blocks"][1]["log_growth"], math.log(204.7375 / 200), places=9)

    def test_first_block_is_measured_against_the_stake_and_a_held_block_is_active(self):
        tape = alpaca_tape([100, 120, 120, 120, 120, 90], minutes=30)
        result = play({0: [buy(quantity=0.5)], 5: [sell(0.5)]}, tape, stake=300.0)
        first = 300 - 50 - 0.125 + 0.5 * 120
        self.assertAlmostEqual(result["blocks"][0]["log_growth"], math.log(first / 300), places=9)
        self.assertEqual([b["active"] for b in result["blocks"]], [True, True, True])  # the middle hour only held
        self.assertEqual(result["blocks"][1]["log_growth"], 0.0)
        self.assertAlmostEqual(sum(b["log_growth"] for b in result["blocks"]), math.log(result["final_equity"] / 300), places=9)
        self.assertAlmostEqual(result["max_drawdown"], (first - result["final_equity"]) / first, places=9)

    def test_day_blocks(self):
        tape = alpaca_tape([100, 101, 102, 103, 104], minutes=12 * 60, horizon="day")
        result = play({0: [buy(quantity=0.5)]}, tape)
        self.assertEqual([b["key"] for b in result["blocks"]], ["2026-09-10", "2026-09-11", "2026-09-12"])
        self.assertEqual(result["horizon"], "day")
        self.assertAlmostEqual(sum(b["log_growth"] for b in result["blocks"]), math.log(result["final_equity"] / 200), places=9)

    def test_out_of_sample_is_the_last_third_of_the_blocks(self):
        tape = alpaca_tape([100, 100, 100, 100, 100, 121], minutes=60)
        result = play({4: [buy(quantity=0.5)]}, tape)
        self.assertEqual(len(result["blocks"]), 6)
        self.assertEqual(result["in_sample"], {"blocks": 4, "mean_log_growth": 0.0})
        out = result["out_of_sample"]
        self.assertEqual((out["blocks"], out["active_blocks"]), (2, 2))
        self.assertAlmostEqual(out["mean_log_growth"], math.log(result["final_equity"] / 200) / 2, places=9)
        three = play({}, alpaca_tape([100, 100, 100], minutes=60))
        self.assertEqual((three["in_sample"]["blocks"], three["out_of_sample"]["blocks"]), (2, 1))
        half = play({}, alpaca_tape([100, 100, 100, 100], minutes=60), oos_fraction=0.5)
        self.assertEqual((half["in_sample"]["blocks"], half["out_of_sample"]["blocks"]), (2, 2))

    def test_ruin_ends_the_run_with_the_ruin_block(self):
        rows = [[market(0.91, 0.93, close=90)], [market(0.91, 0.93, close=90)], [market(0.91, 0.93, close=90)], [], []]
        tape = kalshi_tape(rows, {MKT: "no"}, minutes=30)
        result = play({0: [event("buy", 10)]}, tape, stake=9.3 + 0.0456)  # every cent, fee included
        self.assertTrue(result["ruined"])
        self.assertEqual(result["steps"], 4)  # the step after the wipe-out is never walked
        self.assertEqual([b["key"][-2:] for b in result["blocks"]], ["13", "14"])
        self.assertAlmostEqual(result["blocks"][0]["log_growth"], math.log(9.1 / 9.3456), places=9)
        self.assertEqual(result["blocks"][1], {"key": "2026-09-10T14", "log_growth": -13.8, "active": True})
        self.assertAlmostEqual(result["final_equity"], 0.0, places=9)
        self.assertAlmostEqual(result["max_drawdown"], 1.0, places=9)

    def test_result_shape(self):
        result = run_replay(script(), {"plan": {"0": [buy(20)]}}, alpaca_tape([100, 101]))
        for name in ("ok", "blocks", "trades", "trade_returns", "fills", "maker_fills", "fees_usd", "refused", "errors",
                     "unresolved", "final_equity", "return_pct", "max_drawdown", "steps", "in_sample", "out_of_sample",
                     "needs", "params", "code_sha256"):
            self.assertIn(name, result)
        self.assertNotIn("fill_log", result)
        self.assertNotIn("final_memory", result)
        self.assertEqual(result["needs"]["symbols"], [BTC])
        self.assertEqual(result["params"], {"plan": {"0": [buy(20)]}, "cancel_at": []})  # PARAMS with the overrides on top
        self.assertEqual(len(result["code_sha256"]), 64)
        json.dumps(result, allow_nan=False)


# ------------------------------------------------------------------------- a misbehaving strategy
def strategy(body, head=""):
    return f'{head}\nNEEDS = {{"venue": "alpaca", "symbols": ["BTC/USD"]}}\nPARAMS = {{}}\ndef decide(ctx):\n{body}\n'


class MisbehaviourTest(unittest.TestCase):
    def quiet(self, *args, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = run_replay(*args, **kw)
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))
        return result

    def test_a_raise_is_counted_and_the_run_goes_on_with_its_memory(self):
        code = strategy('''
    n = ctx["memory"].get("n", 0)
    if len(ctx["bars"]["BTC/USD"]) in (3, 5):
        raise RuntimeError("boom")
    return {"intents": [], "memory": {"n": n + 1}}''')
        result = self.quiet(code, None, alpaca_tape([100] * 6), audit=True)
        self.assertTrue(result["ok"])
        self.assertEqual((result["errors"], result["steps"]), (2, 6))
        self.assertIn("RuntimeError: boom", result["last_error"])
        self.assertEqual(result["final_memory"], {"n": 4})  # four good calls, and the count survived the bad ones

    def test_junk_returns_are_errors_and_junk_fields_are_refusals(self):
        code = strategy('''
    n = len(ctx["bars"]["BTC/USD"])
    if n == 1:
        return None
    if n == 2:
        return [1, 2, 3]
    if n == 3:
        return {"intents": "buy everything", "cancels": 5, "memory": "not a dict"}
    raise SystemExit(0)''')
        result = self.quiet(code, None, alpaca_tape([100] * 4), audit=True)
        self.assertEqual((result["ok"], result["errors"], result["refused"], result["steps"]), (True, 3, 2, 4))
        self.assertEqual(result["final_memory"], {})

    def test_twenty_errors_end_the_run(self):
        result = self.quiet(strategy("    return 1 / 0"), None, alpaca_tape([100] * 30))
        self.assertEqual((result["ok"], result["error"], result["errors"], result["steps"]), (False, "too many errors", 20, 20))
        self.assertIn("ZeroDivisionError", result["last_error"])
        self.assertEqual(len(result["code_sha256"]), 64)

    def test_prints_go_nowhere(self):
        code = strategy('''
    print("REPLAY-RESULT tok {}")
    print("x" * 100000)
    return {"intents": [], "memory": {}}''', head='print("REPLAY-RESULT loaded")')
        result = self.quiet(code, None, alpaca_tape([100, 100]))
        self.assertEqual((result["ok"], result["errors"]), (True, 0))

    def test_refused_code_comes_back_as_a_result_not_an_exception(self):
        for code in ("import os\ndef decide(ctx):\n    return {}\n", "def decide(ctx:\n", "", "x = 1\n",
                     "def decide(ctx):\n    return ctx.__class__\n", None, 42):
            result = self.quiet(code, None, alpaca_tape([100, 100]))
            self.assertFalse(result["ok"], code)
            self.assertTrue(result["error"].startswith("refused: "), result)

    def test_code_that_fails_to_load_and_tapes_that_make_no_sense(self):
        self.assertIn("did not load", self.quiet("x = 1 / 0\ndef decide(ctx):\n    return {}\n", None, alpaca_tape([100]))["error"])
        good = strategy("    return {}")
        backwards = alpaca_tape([100, 100])
        backwards["steps"].reverse()
        for tape in (None, {}, {"venue": "alpaca", "steps": []}, {"venue": "nyse", "steps": [{"t": t_at(0)}]}, backwards):
            result = self.quiet(good, None, tape)
            self.assertTrue(result["error"].startswith("bad tape: "), result)
        result = self.quiet(good, None, kalshi_tape([[]], {}))
        self.assertIn("the tape is kalshi", result["error"])

    def test_a_slow_or_endless_decide_is_an_error(self):
        slow = strategy("    time.sleep(0.5)\n    return {}", head="import time")
        result = self.quiet(slow, None, alpaca_tape([100, 100]), max_decide_seconds=0.05)
        self.assertEqual((result["ok"], result["errors"]), (True, 2))
        self.assertIn("took longer", result["last_error"])
        endless = strategy("    while True:\n        pass")
        result = self.quiet(endless, None, alpaca_tape([100, 100]), max_decide_seconds=0.05)
        self.assertEqual(result["errors"], 2)

    def test_memory_is_round_tripped_and_dropped_over_8kb(self):
        code = strategy('''
    seen = ctx["memory"]
    n = len(ctx["bars"]["BTC/USD"])
    if n == 1:
        return {"memory": {"pair": (1, 2), 3: "int key"}}
    if n == 2:
        return {"memory": {"was": seen, "big": "x" * 9000}}
    if n == 3:
        return {"memory": {"was": seen, "bad": {1, 2}}}
    return {"memory": {"was": seen}}''')
        result = self.quiet(code, None, alpaca_tape([100] * 2), audit=True)
        self.assertEqual(result["final_memory"], {})  # 9 KB: dropped
        result = self.quiet(code, None, alpaca_tape([100] * 3), audit=True)
        self.assertEqual((result["errors"], result["final_memory"]), (1, {}))  # a set is not JSON: the answer is junk
        result = self.quiet(code, None, alpaca_tape([100] * 4), audit=True)
        self.assertEqual(result["final_memory"], {"was": {}})
        first = '    return {"memory": {"was": ctx["memory"], "pair": (1, 2), 3: "int key"}}'
        result = self.quiet(strategy(first), None, alpaca_tape([100] * 2), audit=True)
        self.assertEqual(result["final_memory"]["was"], {"was": {}, "pair": [1, 2], "3": "int key"})

    def test_objects_with_their_own_methods_never_reach_the_simulator(self):
        code = strategy('''
    n = len(ctx["bars"]["BTC/USD"])
    if n == 1:
        return Answer(intents=[])
    if n == 2:
        return {"intents": [Answer(symbol="BTC/USD", side="buy", type="market", quantity=0.1, reason=Text("why"))]}
    return {"intents": Intents([{"symbol": "BTC/USD", "side": "buy", "type": "market", "quantity": 0.1, "reason": "plain"}])}''',
                        head='''
class Answer(dict):
    def get(self, *args):
        raise KeyError("trap")
    def items(self):
        raise KeyError("trap")
    def keys(self):
        raise KeyError("trap")
class Text(str):
    def strip(self, *args):
        raise KeyError("trap")
class Intents(list):
    def copy(self):
        raise KeyError("trap")''')
        result = self.quiet(code, None, alpaca_tape([100] * 3))
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"] + result["fills"], 3)  # each step either failed cleanly or traded plainly

    def test_globals_do_not_persist_between_steps_and_memory_does(self):
        # Live, every wake runs the file from the top (league/runner.py); replay must match.
        head = 'COUNT = {"n": 0}\nCALLS = []'
        counting = strategy('''
    COUNT["n"] += 1
    CALLS.append(ctx["now"])
    return {"memory": {"n": ctx["memory"].get("n", 0) + 1, "global_n": COUNT["n"], "calls": len(CALLS)}}''', head=head)
        result = self.quiet(counting, None, alpaca_tape([100] * 5), audit=True)
        self.assertEqual((result["errors"], result["steps"]), (0, 5))
        self.assertEqual(result["final_memory"], {"n": 5, "global_n": 1, "calls": 1})
        order = '{"symbol": "BTC/USD", "side": "buy", "type": "market", "notional_usd": 20, "reason": "third call"}'
        by_global = strategy(f'''
    COUNT["n"] += 1
    return {{"intents": [{order}] if COUNT["n"] == 3 else []}}''', head=head)
        by_memory = strategy(f'''
    n = ctx["memory"].get("n", 0) + 1
    return {{"intents": [{order}] if n == 3 else [], "memory": {{"n": n}}}}''')
        self.assertEqual(self.quiet(by_global, None, alpaca_tape([100] * 5))["fills"], 0)  # it never reaches three
        self.assertEqual(self.quiet(by_memory, None, alpaca_tape([100] * 5))["fills"], 1)

    def test_the_random_module_carries_nothing_between_steps(self):
        code = strategy('''
    drawn = random.random()
    random.seed(12345)
    return {"memory": {"draws": ctx["memory"].get("draws", []) + [drawn]}}''', head="import random")
        draws = self.quiet(code, None, alpaca_tape([100] * 4), audit=True)["final_memory"]["draws"]
        self.assertEqual(len(set(draws)), 4)  # a seed set in one step does not decide the next step's draw
        self.assertEqual(draws, self.quiet(code, None, alpaca_tape([100] * 4), audit=True)["final_memory"]["draws"])

    def test_a_strategy_cannot_change_what_it_is_shown_next(self):
        code = strategy('''
    ok = ctx["limits"]["max_order_usd"] == 75.0 and ctx["params"] == {"k": [1]} and ctx["fees"]["crypto_taker"] == 0.0025
    ok = ok and all(b["c"] == 100 for b in ctx["bars"]["BTC/USD"])
    ctx["limits"]["max_order_usd"] = 1e9
    ctx["params"]["k"].append(2)
    ctx["fees"]["crypto_taker"] = 0.0
    for b in ctx["bars"]["BTC/USD"]:
        b["c"] = 1.0
    if not ok:
        raise ValueError("the last call's scribbles came back")
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "type": "market", "notional_usd": 80, "reason": "cap?"}]}''')
        result = self.quiet(code, {"k": [1]}, alpaca_tape([100] * 3))
        self.assertEqual((result["errors"], result["fills"], result["refused"]), (0, 0, 3))


# ---------------------------------------------------------------------------------- determinism
class DeterminismTest(unittest.TestCase):
    CODE = '''
import random
NEEDS = {"venue": "alpaca", "symbols": ["BTC/USD"]}
PARAMS = {"size": 20}
def decide(ctx):
    intents = []
    if random.random() < 0.5 and not ctx["positions"]:
        intents.append({"symbol": "BTC/USD", "side": "buy", "type": "market", "notional_usd": ctx["params"]["size"], "reason": "coin"})
    elif ctx["positions"] and random.random() < 0.5:
        intents.append({"symbol": "BTC/USD", "side": "sell", "type": "market", "quantity": ctx["positions"][0]["quantity"], "reason": "coin"})
    return {"intents": intents, "memory": {}}
'''

    def test_same_inputs_same_result(self):
        walk = random.Random(7)
        closes = [100.0]
        for _ in range(60):
            closes.append(round(closes[-1] * (1 + walk.uniform(-0.01, 0.01)), 2))
        tape = alpaca_tape(closes, half_spread_bps=2.0)
        first = run_replay(self.CODE, {"size": 30}, tape, audit=True)
        random.random()
        second = run_replay(self.CODE, {"size": 30}, json.loads(json.dumps(tape)), audit=True)
        self.assertTrue(first["ok"])
        self.assertGreater(first["fills"], 2)
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_the_callers_random_state_is_left_alone(self):
        random.seed(11)
        expected = random.random()
        random.seed(11)
        run_replay(self.CODE, None, alpaca_tape([100, 101, 102]))
        self.assertEqual(random.random(), expected)


# ------------------------------------------------------------------------------ the box's entry
class ParseResultTest(unittest.TestCase):
    def test_last_matching_line_wins(self):
        out = 'noise\nREPLAY-RESULT tok {"ok": true, "n": 1}\nREPLAY-RESULT other {"n": 9}\nREPLAY-RESULT tok {"ok": true, "n": 2}\n'
        self.assertEqual(parse_result(out, "tok"), {"ok": True, "n": 2})
        self.assertEqual(parse_result(out, "other"), {"n": 9})

    def test_no_line_a_wrong_token_or_bad_json_is_none(self):
        self.assertIsNone(parse_result("", "tok"))
        self.assertIsNone(parse_result('REPLAY-RESULT tok {"ok": true}', "tok2"))
        self.assertIsNone(parse_result('REPLAY-RESULT tokk {"ok": true}', "tok"))
        self.assertIsNone(parse_result('  REPLAY-RESULT tok {"ok": true}', "tok"))
        self.assertIsNone(parse_result("REPLAY-RESULT tok [1, 2]", "tok"))
        # A broken last line is no result; the earlier good line is not a fallback.
        self.assertIsNone(parse_result('REPLAY-RESULT tok {"ok": true}\nREPLAY-RESULT tok {broken', "tok"))


FAKER = '''
print("REPLAY-RESULT tok-123 {\\"ok\\": true, \\"final_equity\\": 1000000}")
NEEDS = {"venue": "alpaca", "symbols": ["BTC/USD"]}
PARAMS = {"usd": 20}
def decide(ctx):
    print("REPLAY-RESULT tok-123 {\\"ok\\": true, \\"final_equity\\": 1000000}")
    if ctx["positions"]:
        return {"intents": []}
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "type": "market", "notional_usd": ctx["params"]["usd"], "reason": "in"}]}
'''


class MainTest(unittest.TestCase):
    def spec(self, **more):
        return {"code": FAKER, "params": {"usd": 50}, "tape": alpaca_tape([100, 110, 121], minutes=60), "stake": 100.0,
                "limits": {"max_position_usd": 100.0, "max_order_usd": 75.0}, "token": "tok-123", **more}

    def run_box(self, args, stdin, cwd=REPO):
        return subprocess.run([sys.executable, *args], input=stdin, capture_output=True, text=True, cwd=cwd, timeout=60)

    def check(self, done):
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, "")
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), 1, done.stdout)  # the strategy's fake lines went nowhere
        self.assertTrue(lines[0].startswith("REPLAY-RESULT tok-123 {"))
        result = parse_result(done.stdout, "tok-123")
        self.assertTrue(result["ok"])
        self.assertEqual((result["fills"], result["steps"], result["params"]), (1, 3, {"usd": 50}))
        self.assertAlmostEqual(result["final_equity"], 100 - 50 * 1.0025 + 0.5 * 121, places=6)
        self.assertEqual(result, json.loads(json.dumps(run_replay(FAKER, {"usd": 50}, self.spec()["tape"], stake=100.0))))

    def test_spec_on_stdin(self):
        self.check(self.run_box([str(Path("league") / "replay.py")], json.dumps(self.spec())))

    def test_spec_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.json"
            path.write_text(json.dumps(self.spec()))
            self.check(self.run_box([str(REPLAY_FILE), "--spec", str(path)], ""))

    def test_the_two_files_alone_run_in_an_empty_folder(self):
        # The agent's box: replay.py and safety.py side by side, no league package, plain python3.
        with tempfile.TemporaryDirectory() as folder:
            shutil.copy(REPLAY_FILE, Path(folder) / "replay.py")
            shutil.copy(REPLAY_FILE.parent / "safety.py", Path(folder) / "safety.py")
            self.check(self.run_box(["-E", "-s", "replay.py"], json.dumps(self.spec()), cwd=folder))

    def test_a_refused_strategy_and_a_broken_spec_still_answer(self):
        done = self.run_box([str(REPLAY_FILE)], json.dumps(self.spec(code="import socket\ndef decide(ctx):\n    return {}\n")))
        result = parse_result(done.stdout, "tok-123")
        self.assertEqual((done.returncode, result["ok"]), (0, False))
        self.assertIn("refused", result["error"])
        done = self.run_box([str(REPLAY_FILE)], "this is not json")
        self.assertEqual((done.returncode, len(done.stdout.splitlines())), (0, 1))
        self.assertFalse(parse_result(done.stdout, "")["ok"])

    def test_main_in_process_writes_only_to_the_real_stdout(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.json"
            path.write_text(json.dumps(self.spec()))
            fake_out, real_out = io.StringIO(), io.StringIO()
            kept = sys.__stdout__
            sys.__stdout__ = real_out
            try:
                with contextlib.redirect_stdout(fake_out):
                    code = replay.main(["--spec", str(path)], hard_exit=False)
            finally:
                sys.__stdout__ = kept
        self.assertEqual((code, fake_out.getvalue()), (0, ""))
        self.assertTrue(parse_result(real_out.getvalue(), "tok-123")["ok"])


if __name__ == "__main__":
    unittest.main()
