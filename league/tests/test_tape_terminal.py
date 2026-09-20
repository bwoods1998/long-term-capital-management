"""Closing execution observations must retain available adverse fills without inventing a touch."""
import unittest

from league.replay import run_replay
from league.tapes import KalshiData, iso, parse_time
from league.tests.test_tapes import FakeHistory, candle, settled


BASE = parse_time("2026-09-10T12:00:00Z")
TICKER = "KXBTCD-TAIL-T80000"


def stamp(seconds):
    return iso(BASE + seconds)


def market(close=240, listed=None):
    listed = close if listed is None else listed
    return {"ticker": TICKER, "series": "KXBTCD", "title": "Tail test", "strike": 80000,
            "close_ts": BASE + close, "listed_close_ts": BASE + listed,
            "close_time": stamp(listed), "resolve_ts": BASE + max(close, listed)}


def maker(leg="yes", extra_at_close=False):
    return '''NEEDS = {"venue":"kalshi", "horizon":"hour", "series":["KXBTCD"]}
def decide(ctx):
    sent = ctx.get("memory", {}).get("sent")
    closing = not ctx["markets"]
    intents = [] if sent and not (closing and EXTRA) else [{
        "market":"KXBTCD-TAIL-T80000", "leg":LEG, "side":"buy", "quantity":10,
        "type":"limit", "limit_price":0.90, "reason":"resting tail test"}]
    return {"intents":intents, "memory":{"sent":True, "last_markets":len(ctx["markets"])}}
'''.replace("EXTRA", repr(extra_at_close)).replace("LEG", repr(leg))


class TerminalRangeTest(unittest.TestCase):
    def rows(self, candles, *, close=240, listed=None, end=600, step=300):
        return KalshiData._market_steps(market(close, listed), candles, BASE, BASE + end, step)

    def test_aligned_and_unaligned_closes_keep_the_entire_last_interval(self):
        for close in (240, 300):
            with self.subTest(close=close):
                rows = self.rows([candle(stamp(0), .89, .91),
                                  candle(stamp(close - 60), .4, .5, ask_low=.3, bid_high=.6),
                                  candle(stamp(close), .02, .04, ask_low=.01, bid_high=.07)], close=close)
                self.assertEqual([t for t, row in rows], [BASE, BASE + close])
                terminal = rows[-1][1]
                self.assertEqual((terminal["yes_ask_low"], terminal["yes_bid_high"]), (.01, .6))
                self.assertEqual(terminal["close_time"], stamp(close))
                self.assertEqual(terminal["hours_to_close"], 0)
                self.assertIsNone(terminal["yes_bid"])
                self.assertIsNone(terminal["yes_ask"])

    def test_one_sided_final_candle_keeps_valid_ranges_but_not_post_close_candles(self):
        rows = self.rows([candle(stamp(0), .89, .91),
                          candle(stamp(240), 0, 1, ask_low=.02, bid_high=.97),
                          candle(stamp(241), .01, .99, ask_low=.001, bid_high=.999)])
        self.assertEqual((rows[-1][1]["yes_ask_low"], rows[-1][1]["yes_bid_high"]), (.02, .97))
        self.assertIsNone(rows[-1][1]["yes_bid"])
        self.assertIsNone(rows[-1][1]["yes_ask"])

    def test_missing_final_range_does_not_reuse_a_range_from_before_submission(self):
        rows = self.rows([candle(stamp(0), .89, .91, ask_low=.01, bid_high=.99)])
        self.assertIsNone(rows[-1][1]["yes_ask_low"])
        self.assertIsNone(rows[-1][1]["yes_bid_high"])
        result = run_replay(maker(), {}, {"venue":"kalshi", "horizon":"hour", "results":{TICKER:"no"},
            "steps":[{"t":iso(t), "markets":[row]} for t, row in rows]})
        self.assertTrue(result["ok"])
        self.assertEqual((result["fills"], result["expired_orders"], result["final_equity"]), (0, 1, 200))

    def test_earlier_actual_or_listed_stop_bounds_terminal_history(self):
        for close, listed in ((240, 600), (600, 240)):
            with self.subTest(close=close, listed=listed):
                rows = self.rows([candle(stamp(0), .89, .91), candle(stamp(240), .7, .8),
                                  candle(stamp(300), .01, .02)], close=close, listed=listed)
                self.assertEqual(rows[0][1]["close_time"], stamp(listed))
                self.assertEqual(rows[-1][0], BASE + 240)
                self.assertEqual(rows[-1][1]["close_time"], stamp(240))
                self.assertEqual(rows[-1][1]["yes_ask_low"], .8)

    def test_requested_end_excludes_future_close_and_its_candles(self):
        rows = self.rows([candle(stamp(0), .89, .91), candle(stamp(240), .01, .02)], end=180)
        self.assertEqual([t for t, row in rows], [BASE])
        self.assertEqual(rows[0][1]["yes_ask_low"], .91)
        self.assertEqual(self.rows([candle(stamp(240), .01, .02)]), [])

    def test_coarse_and_one_minute_tapes_both_capture_the_losing_resting_fill(self):
        for leg in ("yes", "no"):
            for step in (60, 300, 1800):
                with self.subTest(leg=leg, step=step):
                    before = (.89, .91) if leg == "yes" else (.09, .11)
                    after = (.01, .02) if leg == "yes" else (.98, .99)
                    history = FakeHistory([settled(TICKER, "no" if leg == "yes" else "yes", stamp(-60), stamp(240))],
                        {TICKER:[candle(stamp(0), *before), candle(stamp(180), *after)]})
                    tape = KalshiData(None, history, clock=lambda: BASE + 600).tape(
                        ["KXBTCD"], start=stamp(0), end=stamp(600), step_seconds=step)
                    result = run_replay(maker(leg, extra_at_close=True), {}, tape, audit=True)
                    self.assertTrue(result["ok"], result)
                    self.assertEqual((result["fills"], result["maker_fills"], result["trades"], result["errors"]), (1, 1, 1, 0))
                    self.assertEqual(result["final_equity"], 191)
                    self.assertEqual(result["final_memory"]["last_markets"], 1)
                    self.assertEqual(result["refusal_reasons"], {})
                    self.assertEqual(len(result["fill_log"]), 1)  # the terminal row cannot open a new order

    def test_terminal_and_another_markets_observation_share_one_ordered_step(self):
        other = "KXBTCD-OTHER-T81000"
        history = FakeHistory([settled(TICKER, "no", stamp(-60), stamp(300)),
                               settled(other, "yes", stamp(-60), stamp(600))],
            {TICKER:[candle(stamp(0), .89, .91), candle(stamp(300), .01, .02)],
             other:[candle(stamp(0), .4, .5), candle(stamp(300), .5, .6)]})
        tape = KalshiData(None, history, clock=lambda: BASE + 900).tape(["KXBTCD"], start=stamp(0), end=stamp(600))
        times = [s["t"] for s in tape["steps"]]
        self.assertEqual(times, [stamp(0), stamp(300), stamp(600)])
        middle = {m["market"]:m for m in tape["steps"][1]["markets"]}
        self.assertIsNone(middle[TICKER]["yes_ask"])
        self.assertEqual(middle[other]["yes_ask"], .6)
        self.assertNotIn("execution_only", tape["steps"][1])
        self.assertTrue(tape["steps"][2]["execution_only"])
        code = '''NEEDS = {"venue":"kalshi", "horizon":"hour", "series":["KXBTCD"]}
def decide(ctx):
    return {"intents":[{"market":"KXBTCD-TAIL-T80000", "leg":"yes", "side":"buy", "quantity":10,
                        "type":"limit", "limit_price":0.90, "reason":"attempt also at close"}],
            "memory":{"times":ctx.get("memory", {}).get("times", []) + [ctx["now"]],
                      "markets":[m["market"] for m in ctx["markets"]]}}
'''
        result = run_replay(code, {}, tape, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["final_memory"], {"times":[stamp(0), stamp(300)], "markets":[other]})
        self.assertEqual((result["fills"], result["final_equity"]), (1, 191))
        self.assertEqual(result["refusal_reasons"], {"the market has closed":1})

    def test_off_grid_close_does_not_create_a_wake_that_cancels_another_markets_order(self):
        other = "KXBTCD-OTHER-T81000"
        history = FakeHistory([settled(TICKER, "yes", stamp(-60), stamp(240)),
                               settled(other, "no", stamp(-60), stamp(600))],
            {TICKER:[candle(stamp(0), .89, .91)],
             other:[candle(stamp(0), .89, .91), candle(stamp(300), .01, .02)]})
        tape = KalshiData(None, history, clock=lambda: BASE + 900).tape(["KXBTCD"], start=stamp(0), end=stamp(600))
        code = '''import random
NEEDS = {"venue":"kalshi", "horizon":"hour", "series":["KXBTCD"]}
def decide(ctx):
    previous = ctx.get("memory", {})
    intents = [] if previous else [{"market":"KXBTCD-OTHER-T81000", "leg":"yes", "side":"buy", "quantity":10,
                                   "type":"limit", "limit_price":0.90, "reason":"the other market"}]
    cancels = [o["order_id"] for o in ctx["open_orders"]] if not ctx["markets"] else []
    return {"intents":intents, "cancels":cancels, "memory":{"draws":previous.get("draws", []) + [random.random()],
            "times":previous.get("times", []) + [ctx["now"]]}}
'''
        result = run_replay(code, {}, tape, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual((result["fills"], result["trades"], result["final_equity"]), (1, 1, 191))
        self.assertEqual(result["final_memory"]["times"], [stamp(0), stamp(300)])
        without_terminals = {**tape, "steps":[s for s in tape["steps"] if not s.get("execution_only")]}
        regular = run_replay(code, {}, without_terminals, audit=True)
        self.assertEqual(result["final_memory"], regular["final_memory"])


if __name__ == "__main__":
    unittest.main()
