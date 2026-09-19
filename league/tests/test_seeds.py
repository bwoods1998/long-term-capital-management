"""The founding seeds, tested exactly as they run: every decision goes through
`league.runner.decide(code, ctx)` with a hand-built `ctx`, and every answer is checked against
the rules a seed must never break (`_check`): a reason on every intent, no sell that is not the
whole holding exactly, no buy over the order cap or the cash, no post-only order at or through
the touch, a thought every time."""

import unittest
from datetime import datetime, timedelta, timezone

from league import runner
from league.safety import check_code
from league.seeds import SEEDS, all_seeds, load

LIMITS = {"max_position_usd": 100.0, "max_order_usd": 75.0}
FEES = {"crypto_taker": 0.0025, "crypto_maker": 0.0015, "kalshi_taker_rate": 0.07}

# New York is UTC-4 on these September dates. Sept 21, 2026 is a Monday.
MON_0940 = "2026-09-21T13:40:00Z"
MON_1000 = "2026-09-21T14:00:00Z"
MON_1100 = "2026-09-21T15:00:00Z"
MON_1545 = "2026-09-21T19:45:00Z"
MON_1555 = "2026-09-21T19:55:00Z"
MON_0800 = "2026-09-21T12:00:00Z"   # before the open
MON_1630 = "2026-09-21T20:30:00Z"   # after the close
SAT_1100 = "2026-09-19T15:00:00Z"   # a Saturday
THANKSGIVING_1100 = "2026-11-26T16:00:00Z"  # a Thursday, a full-day holiday (UTC-5 by then)
CLOSED = {"before the open": MON_0800, "after the close": MON_1630, "Saturday": SAT_1100, "Thanksgiving": THANKSGIVING_1100}
FRIDAY_BAR = "2026-09-19T04:00:00Z"  # Friday's daily bar is stamped with its close: midnight New York


# ------------------------------------------------------------------------------------ helpers
def when(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(now, **delta):
    return iso(when(now) - timedelta(**delta))


def make_bars(closes, end, step_seconds, width=0.001, volume=1000.0):
    """Closed bars, oldest first, stamped with their close time; the last one closes at `end`."""
    out, last = [], when(end)
    for index, close in enumerate(closes):
        before = closes[index - 1] if index else close
        out.append({"t": iso(last - timedelta(seconds=step_seconds * (len(closes) - 1 - index))), "o": before,
                    "h": max(before, close) * (1 + width), "l": min(before, close) * (1 - width), "c": close, "v": volume})
    return out


def wiggle(count, base=100.0, amp=0.3):
    """A flat series that alternates `amp` above and below `base`: mean `base`, sd `amp`."""
    return [base + (amp if index % 2 else -amp) for index in range(count)]


def ramp(count, start, step):
    return [start + step * index for index in range(count)]


def position(symbol, quantity, cost, opened_at, mark=None):
    return {"symbol": symbol, "quantity": quantity, "average_cost": cost, "mark": cost if mark is None else mark,
            "opened_at": opened_at, "reason": "test"}


def order(symbol, side, quantity, price, submitted_at, order_id="ord-1"):
    return {"order_id": order_id, "symbol": symbol, "side": side, "quantity": quantity, "limit_price": price,
            "filled": 0.0, "submitted_at": submitted_at}


def alpaca_ctx(now, bars, positions=(), orders=(), cash=200.0, memory=None, params=None, limits=None, quotes=None):
    touch = {s: {"bid": rows[-1]["c"] * 0.9999, "ask": rows[-1]["c"] * 1.0001} for s, rows in bars.items() if rows}
    touch.update(quotes or {})
    return {"now": now, "venue": "alpaca", "rung": 1, "params": dict(params or {}), "memory": dict(memory or {}),
            "cash": cash, "equity": 200.0, "limits": dict(limits or LIMITS), "fees": dict(FEES),
            "positions": list(positions), "open_orders": list(orders), "bars": bars, "quotes": touch}


def market(ticker, yes_bid, yes_ask, hours=1.0, volume=5000, series="KXBTCD"):
    return {"market": ticker, "series": series, "title": ticker, "yes_bid": yes_bid, "yes_ask": yes_ask,
            "close_time": "2026-09-21T16:00:00Z", "hours_to_close": hours, "volume_24h": volume,
            "open_interest": 1000, "strike": 80000.0}


def event_position(ticker, leg, quantity, cost):
    return {"market": ticker, "leg": leg, "quantity": quantity, "average_cost": cost, "mark": cost,
            "opened_at": MON_1000, "reason": "test"}


def event_order(ticker, leg, quantity, price, submitted_at, order_id="ord-1"):
    return {"order_id": order_id, "market": ticker, "leg": leg, "side": "buy", "quantity": quantity,
            "limit_price": price, "filled": 0.0, "submitted_at": submitted_at}


def kalshi_ctx(markets, positions=(), orders=(), cash=200.0, params=None, limits=None, now=MON_1000):
    return {"now": now, "venue": "kalshi", "rung": 1, "params": dict(params or {}), "memory": {}, "cash": cash,
            "equity": 200.0, "limits": dict(limits or LIMITS), "fees": dict(FEES), "positions": list(positions),
            "open_orders": list(orders), "markets": list(markets)}


class SeedCase(unittest.TestCase):
    SEED = ""

    def run_seed(self, ctx, seed=None):
        out = runner.decide(load(seed or self.SEED), ctx)
        self.assertTrue(out.get("ok"), out.get("error"))
        self._check(out, ctx)
        return out

    def _check(self, out, ctx):
        """What no seed may ever do, whatever the test is about."""
        self.assertTrue(out["thought"].strip(), "a thought is always given")
        self.assertLessEqual(len(out["intents"]), 8)
        limits, asks = ctx.get("limits") or LIMITS, {}
        for row in ctx.get("markets") or []:
            if isinstance(row, dict) and isinstance(row.get("yes_bid"), float) and isinstance(row.get("yes_ask"), float):
                asks[(row["market"], "yes")], asks[(row["market"], "no")] = row["yes_ask"], 1.0 - row["yes_bid"]
        spent = 0.0
        for intent in out["intents"]:
            self.assertIn(intent["side"], ("buy", "sell"))
            self.assertIn(intent["type"], ("market", "limit"))
            self.assertGreater(len(intent.get("reason") or ""), 30, "a specific reason")
            self.assertTrue(any(ch.isdigit() for ch in intent["reason"]), "a reason carries its numbers")
            self.assertNotEqual("quantity" in intent, "notional_usd" in intent, "quantity or notional_usd, one of them")
            key = "market" if ctx.get("venue") == "kalshi" else "symbol"
            if intent["side"] == "sell":
                held = [x for x in ctx.get("positions") or [] if x.get(key) == intent[key] and x.get("leg") == intent.get("leg")]
                self.assertEqual(len(held), 1, "a sell closes a holding")
                self.assertEqual(intent.get("quantity"), held[0]["quantity"], "a sell is the whole holding, exactly as given")
                continue
            dollars = intent["notional_usd"] if "notional_usd" in intent else intent["quantity"] * intent["limit_price"]
            self.assertGreaterEqual(dollars, 1.0)
            self.assertLessEqual(dollars, limits["max_order_usd"] + 1e-9)
            self.assertLessEqual(dollars, limits["max_position_usd"] + 1e-9)
            spent += dollars
            if ctx.get("venue") == "kalshi":
                self.assertEqual(intent["quantity"], int(intent["quantity"]), "whole contracts")
                self.assertGreaterEqual(intent["limit_price"], 0.15)
            if intent.get("post_only"):
                self.assertEqual(intent["type"], "limit")
                self.assertLess(intent["limit_price"], asks[(intent["market"], intent["leg"])] - 1e-9, "post-only never crosses")
        if spent:
            self.assertLessEqual(spent, float(ctx.get("cash") or 0.0) * 0.98 + 1e-6, "2% of the cash is left alone")

    def buys(self, out):
        return [i for i in out["intents"] if i["side"] == "buy"]

    def sells(self, out):
        return [i for i in out["intents"] if i["side"] == "sell"]


# ------------------------------------------------------------------------------- the registry
class RegistryTests(unittest.TestCase):
    def test_twelve_seeds_with_unique_names_and_files(self):
        self.assertEqual(len(SEEDS), 12)
        self.assertEqual(len({row["name"] for row in SEEDS}), 12)
        self.assertEqual(len({row["file"] for row in SEEDS}), 12)
        for row in SEEDS:
            self.assertEqual(set(row), {"name", "family", "file", "why"})
            self.assertGreater(len(row["why"]), 40)

    def test_families_are_the_agreed_ones(self):
        families = {row["name"]: row["family"] for row in SEEDS}
        self.assertEqual(families, {
            "favorites-maker": "kalshi-favorites", "favorites-no": "kalshi-favorites", "favorites-daily": "kalshi-favorites",
            "hourly-quotes": "kalshi-quotes", "crypto-reversion": "crypto-reversion", "crypto-trend": "crypto-trend",
            "crypto-dip-limit": "crypto-reversion", "crypto-pairs": "crypto-pairs", "equity-overnight": "equity-overnight",
            "equity-trend": "equity-trend", "equity-rsi2": "equity-reversion", "equity-vwap": "equity-intraday"})

    def test_load_and_all_seeds(self):
        rows = all_seeds()
        self.assertEqual([r["name"] for r in rows], [r["name"] for r in SEEDS])
        for row in rows:
            self.assertEqual(row["code"], load(row["name"]))
            self.assertIn("def decide(ctx):", row["code"])
        self.assertNotIn("code", SEEDS[0], "all_seeds copies the rows")
        with self.assertRaises(KeyError):
            load("no-such-seed")

    def test_every_seed_passes_the_safety_check(self):
        for row in all_seeds():
            with self.subTest(row["name"]):
                check_code(row["code"])

    def test_every_seed_is_short_and_explains_itself_first(self):
        for row in all_seeds():
            with self.subTest(row["name"]):
                lines = row["code"].splitlines()
                self.assertLessEqual(len(lines), 160)
                self.assertTrue(lines[0].startswith(f"# {row['name']}:"), "the header names the seed")
                header = [line for line in lines[:40] if line.startswith("#")]
                self.assertGreaterEqual(len(header), 15, "a plain-English header: idea, evidence, needs, entries, exits")
                for word in ("THE IDEA", "THE EVIDENCE", "WHAT IT NEEDS", "WHEN IT TRADES", "HOW IT EXITS"):
                    self.assertIn(word, "\n".join(header))

    def test_needs_and_params_are_valid(self):
        expected = {
            "favorites-maker": ("kalshi", "hour", "favorites"), "favorites-no": ("kalshi", "hour", "favorites-no"),
            "favorites-daily": ("kalshi", "day", "favorites-daily"), "hourly-quotes": ("kalshi", "hour", "maker"),
            "crypto-reversion": ("alpaca", "hour", "reversion"), "crypto-trend": ("alpaca", "hour", "trend"),
            "crypto-dip-limit": ("alpaca", "hour", "maker-reversion"), "crypto-pairs": ("alpaca", "hour", "pairs"),
            "equity-overnight": ("alpaca", "day", "overnight"), "equity-trend": ("alpaca", "day", "trend"),
            "equity-rsi2": ("alpaca", "day", "reversion"), "equity-vwap": ("alpaca", "hour", "intraday-reversion")}
        for row in all_seeds():
            with self.subTest(row["name"]):
                found = runner.needs_of(row["code"])
                self.assertTrue(found["ok"], found.get("error"))
                needs, params = found["needs"], found["params"]
                self.assertEqual((needs["venue"], needs["horizon"], needs["style"]), expected[row["name"]])
                self.assertLessEqual(len(needs["style"]), 24)
                self.assertIsInstance(needs["wake_minutes"], int)
                self.assertTrue(5 <= needs["wake_minutes"] <= 1440)
                self.assertTrue(params and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in params.values()),
                                "PARAMS are plain numbers a mutation can move")
                self.assertGreaterEqual(params["notional_usd"], 1.0)
                if needs["venue"] == "alpaca":
                    self.assertTrue(needs["symbols"] and all(isinstance(s, str) for s in needs["symbols"]))
                    self.assertIn(needs["bars"]["timeframe"], ("1Min", "5Min", "15Min", "1Hour", "1Day"))
                    self.assertTrue(1 <= needs["bars"]["limit"] <= 500)
                else:
                    self.assertTrue(needs["series"] and all(isinstance(s, str) for s in needs["series"]))
                    self.assertGreater(needs["max_hours_to_close"], 0)

    def test_the_niches_are_all_different(self):
        niches = [tuple(runner.needs_of(r["code"])["needs"][k] for k in ("venue", "horizon", "style")) for r in all_seeds()]
        self.assertEqual(len(set(niches)), 12)

    def test_spec_details_of_needs(self):
        needs = {row["name"]: runner.needs_of(row["code"])["needs"] for row in all_seeds()}
        self.assertEqual(needs["favorites-maker"]["series"], ["KXBTCD", "KXETHD"])
        self.assertEqual(needs["favorites-daily"]["series"], ["KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHDEN",
                                                              "KXHIGHLAX", "KXHIGHPHIL", "KXWTI", "KXGOLDD"])
        self.assertEqual((needs["favorites-daily"]["max_hours_to_close"], needs["favorites-daily"]["wake_minutes"]), (30, 60))
        self.assertEqual(needs["hourly-quotes"]["series"], ["KXBTCD"])
        self.assertEqual(needs["crypto-reversion"]["bars"], {"timeframe": "1Hour", "limit": 72})
        self.assertEqual(needs["crypto-trend"]["bars"], {"timeframe": "1Hour", "limit": 120})
        self.assertEqual(needs["crypto-dip-limit"]["bars"]["timeframe"], "15Min")
        self.assertEqual(sorted(needs["crypto-pairs"]["symbols"]), ["BTC/USD", "ETH/USD"])
        self.assertEqual((needs["equity-overnight"]["bars"], needs["equity-overnight"]["wake_minutes"]), ({"timeframe": "1Day", "limit": 30}, 10))
        self.assertEqual(needs["equity-trend"]["symbols"], ["SPY", "QQQ", "IWM", "TLT", "GLD"])
        self.assertEqual(needs["equity-rsi2"]["bars"], {"timeframe": "1Day", "limit": 210})
        self.assertEqual((needs["equity-vwap"]["bars"], needs["equity-vwap"]["wake_minutes"]), ({"timeframe": "5Min", "limit": 100}, 5))

    def test_missing_and_broken_data_never_raises(self):
        junk = [
            {},
            {"now": None, "positions": None, "open_orders": None, "bars": None, "quotes": None, "markets": None, "limits": None, "memory": None},
            {"now": MON_1100, "memory": ["not", "a", "dict"]},
            {"now": "not a time", "cash": "lots", "bars": {"BTC/USD": [None, {}, {"c": "x"}], "SPY": "nope"}, "markets": [None, {}, {"market": "M"}],
             "positions": [None, {"symbol": "SPY"}, {"market": "M", "quantity": "many"}], "open_orders": [None, {"order_id": 7}], "memory": {"acted": 3, "stopped": [], "done": 9}},
            {"now": MON_1100, "cash": 200.0, "limits": LIMITS, "bars": {s: [] for s in ("BTC/USD", "ETH/USD", "SOL/USD", "SPY", "QQQ", "IWM", "TLT", "GLD")},
             "markets": [market("KXBTCD-A", None, None), market("KXBTCD-B", 0.95, 0.93), market("KXBTCD-C", 0.0, 1.0)]},
            {"now": MON_1100, "cash": 200.0, "limits": LIMITS, "bars": {s: make_bars([100.0] * 3, MON_1100, 300) for s in ("BTC/USD", "ETH/USD", "SPY", "QQQ")}},
        ]
        for row in all_seeds():
            for index, ctx in enumerate(junk):
                with self.subTest(seed=row["name"], ctx=index):
                    out = runner.decide(row["code"], ctx)
                    self.assertTrue(out.get("ok"), out.get("error"))
                    self.assertEqual(out["intents"], [])
                    self.assertTrue(out["thought"].strip())

    def test_decisions_are_deterministic(self):
        kalshi = kalshi_ctx([market("KXBTCD-A", 0.93, 0.95), market("KXBTCD-B", 0.05, 0.07), market("KXBTCD-C", 0.45, 0.52, hours=0.6)])
        bars = {s: make_bars(wiggle(120) + [96.0], MON_1100, 3600) for s in ("BTC/USD", "ETH/USD", "SOL/USD", "SPY", "QQQ", "IWM", "TLT", "GLD")}
        for row in all_seeds():
            with self.subTest(row["name"]):
                ctx = kalshi if runner.needs_of(row["code"])["needs"]["venue"] == "kalshi" else alpaca_ctx(MON_1100, bars)
                first, second = runner.decide(row["code"], ctx), runner.decide(row["code"], ctx)
                first.pop("seconds"), second.pop("seconds")
                self.assertEqual(first, second)

    def test_no_seed_reads_the_wall_clock_or_draws_random_numbers(self):
        for row in all_seeds():
            with self.subTest(row["name"]):
                for banned in ("import random", "import time", "datetime.now", "utcnow", "today()"):
                    self.assertNotIn(banned, row["code"])


# -------------------------------------------------------------------------- kalshi favourites
class FavoritesMakerTests(SeedCase):
    SEED = "favorites-maker"
    LEG = "yes"
    SERIES = "KXBTCD"

    def fav(self, ticker="KXBTCD-A", price=0.93, spread=0.02, **more):
        """A market whose favourite leg is bid at `price`."""
        more.setdefault("series", self.SERIES)
        more.setdefault("hours", 2.0)
        if self.LEG == "yes":
            return market(ticker, price, round(price + spread, 4), **more)
        return market(ticker, round(1.0 - price - spread, 4), round(1.0 - price, 4), **more)

    def test_rests_a_post_only_bid_at_the_touch_on_a_favourite(self):
        out = self.run_seed(kalshi_ctx([self.fav(price=0.93)]))
        self.assertEqual(len(out["intents"]), 1)
        intent = out["intents"][0]
        self.assertEqual((intent["market"], intent["leg"], intent["side"], intent["type"]), ("KXBTCD-A", self.LEG, "buy", "limit"))
        self.assertTrue(intent["post_only"])
        self.assertAlmostEqual(intent["limit_price"], 0.93)
        self.assertEqual(intent["quantity"], 10)  # $10 at 93 cents, whole contracts
        self.assertIn("0.93", intent["reason"])
        self.assertEqual(out["cancels"], [])

    def test_the_band_is_90_to_97_cents(self):
        for price, wanted in ((0.89, 0), (0.90, 1), (0.97, 1), (0.98, 0), (0.50, 0), (0.07, 0)):
            with self.subTest(price=price):
                out = self.run_seed(kalshi_ctx([self.fav(price=price, spread=0.01)]))
                self.assertEqual(len(out["intents"]), wanted)

    def test_stays_out_of_wide_thin_or_badly_timed_markets(self):
        for name, row in (("wide spread", self.fav(spread=0.04)), ("thin", self.fav(volume=10)),
                          ("too close to the close", self.fav(hours=0.01)), ("too far out", self.fav(hours=200.0))):
            with self.subTest(name):
                self.assertEqual(self.run_seed(kalshi_ctx([row]))["intents"], [])

    def test_never_adds_to_a_market_it_holds_or_has_an_order_in(self):
        held = self.run_seed(kalshi_ctx([self.fav()], positions=[event_position("KXBTCD-A", self.LEG, 5, 0.92)]))
        self.assertEqual(held["intents"], [])
        other_leg = self.run_seed(kalshi_ctx([self.fav()], positions=[event_position("KXBTCD-A", "no" if self.LEG == "yes" else "yes", 5, 0.05)]))
        self.assertEqual(other_leg["intents"], [])
        working = self.run_seed(kalshi_ctx([self.fav()], orders=[event_order("KXBTCD-A", self.LEG, 10, 0.93, ago(MON_1000, minutes=5))]))
        self.assertEqual((working["intents"], working["cancels"]), ([], []))

    def test_max_open_counts_holdings_and_resting_orders(self):
        rows = [self.fav(f"KXBTCD-{n}", volume=9000 - n) for n in range(8)]
        self.assertEqual(len(self.run_seed(kalshi_ctx(rows, params={"max_open": 4}))["intents"]), 4)
        out = self.run_seed(kalshi_ctx(rows, params={"max_open": 4}, positions=[event_position("KXBTCD-OLD", self.LEG, 5, 0.9)],
                                       orders=[event_order("KXBTCD-0", self.LEG, 10, 0.93, ago(MON_1000, minutes=1))]))
        self.assertEqual([i["market"] for i in out["intents"]], ["KXBTCD-1", "KXBTCD-2"], "two slots left, busiest first, never the market with an order")
        full = self.run_seed(kalshi_ctx(rows, params={"max_open": 1}, positions=[event_position("KXBTCD-OLD", self.LEG, 5, 0.9)]))
        self.assertEqual(full["intents"], [])

    def test_cancels_stale_orders_and_does_not_requote_the_same_wake(self):
        orders = [event_order("KXBTCD-A", self.LEG, 10, 0.91, ago(MON_1000, minutes=600), "ord-old"),
                  event_order("KXBTCD-B", self.LEG, 10, 0.93, ago(MON_1000, minutes=2), "ord-new")]
        out = self.run_seed(kalshi_ctx([self.fav("KXBTCD-A"), self.fav("KXBTCD-B")], orders=orders))
        self.assertEqual(out["cancels"], ["ord-old"])
        self.assertEqual(out["intents"], [])

    def test_holds_to_settlement_and_never_sells(self):
        out = self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.30, 0.33, hours=2.0, series=self.SERIES)],
                                       positions=[event_position("KXBTCD-A", self.LEG, 10, 0.93)]))
        self.assertEqual(out["intents"], [])

    def test_sizes_by_cash_and_limits_and_skips_under_a_dollar(self):
        self.assertEqual(self.run_seed(kalshi_ctx([self.fav()], cash=5.0))["intents"][0]["quantity"], 5)  # 4.90 / 0.93
        self.assertEqual(self.run_seed(kalshi_ctx([self.fav()], cash=0.99))["intents"], [])
        capped = self.run_seed(kalshi_ctx([self.fav()], limits={"max_position_usd": 100.0, "max_order_usd": 3.0}))
        self.assertEqual(capped["intents"][0]["quantity"], 3)
        position_cap = self.run_seed(kalshi_ctx([self.fav()], limits={"max_position_usd": 2.0, "max_order_usd": 75.0}))
        self.assertEqual(position_cap["intents"][0]["quantity"], 2)
        reserved = [event_order(f"KXBTCD-R{n}", self.LEG, 100, 0.95, ago(MON_1000, minutes=1), f"ord-{n}") for n in range(2)]
        self.assertEqual(self.run_seed(kalshi_ctx([self.fav()], orders=reserved, cash=191.0, params={"max_open": 9}))["intents"], [],
                         "cash already reserved by resting bids is not spent twice")

    def test_many_markets_never_spend_more_than_the_cash(self):
        rows = [self.fav(f"KXBTCD-{n}") for n in range(8)]
        out = self.run_seed(kalshi_ctx(rows, cash=25.0, params={"max_open": 8}))
        self.assertLessEqual(sum(i["quantity"] * i["limit_price"] for i in out["intents"]), 24.5)
        self.assertGreaterEqual(len(out["intents"]), 2)


class FavoritesNoTests(FavoritesMakerTests):
    SEED = "favorites-no"
    LEG = "no"

    def test_the_no_touch_is_the_mirror_of_the_yes_touch(self):
        out = self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.05, 0.07, hours=2.0)]))
        intent = out["intents"][0]
        self.assertEqual(intent["leg"], "no")
        self.assertAlmostEqual(intent["limit_price"], 0.93)   # NO bid = 1 - YES ask
        self.assertLess(intent["limit_price"], 1.0 - 0.05)     # under the NO ask = 1 - YES bid

    def test_a_yes_ask_over_ten_cents_is_not_a_no_favourite(self):
        self.assertEqual(self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.10, 0.12, hours=2.0)]))["intents"], [])
        self.assertEqual(len(self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.08, 0.10, hours=2.0)]))["intents"]), 1)

    def test_it_never_buys_the_yes_longshot(self):
        out = self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.05, 0.07, hours=2.0), market("KXBTCD-B", 0.93, 0.95, hours=2.0)]))
        self.assertEqual([(i["market"], i["leg"]) for i in out["intents"]], [("KXBTCD-A", "no")])


class FavoritesDailyTests(FavoritesMakerTests):
    SEED = "favorites-daily"
    SERIES = "KXHIGHNY"

    def test_it_takes_markets_a_day_away(self):
        self.assertEqual(len(self.run_seed(kalshi_ctx([self.fav(hours=26.0)]))["intents"]), 1)
        self.assertEqual(self.run_seed(kalshi_ctx([self.fav(hours=31.0)]))["intents"], [])


# ------------------------------------------------------------------------------ hourly quotes
class HourlyQuotesTests(SeedCase):
    SEED = "hourly-quotes"

    def test_quotes_both_legs_inside_a_wide_undecided_market(self):
        out = self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.45, 0.52, hours=0.6)]))
        legs = {i["leg"]: i for i in out["intents"]}
        self.assertEqual(set(legs), {"yes", "no"})
        self.assertAlmostEqual(legs["yes"]["limit_price"], 0.46)
        self.assertAlmostEqual(legs["no"]["limit_price"], 0.49)   # (1 - 0.52) + 0.01
        self.assertLessEqual(legs["yes"]["limit_price"] + legs["no"]["limit_price"], 0.98 + 1e-9)
        self.assertEqual(legs["yes"]["quantity"], legs["no"]["quantity"], "a pair needs the same count on both legs")
        self.assertEqual(legs["yes"]["quantity"], 10)  # $5 on the dearer leg at 0.49
        self.assertTrue(all(i["post_only"] and i["side"] == "buy" for i in out["intents"]))

    def test_stays_out_when_the_market_does_not_qualify(self):
        rows = {"tight spread": market("KXBTCD-A", 0.48, 0.51, hours=0.6), "decided": market("KXBTCD-A", 0.80, 0.88, hours=0.6),
                "cheap": market("KXBTCD-A", 0.10, 0.18, hours=0.6), "last twenty minutes": market("KXBTCD-A", 0.45, 0.52, hours=0.3),
                "over 58 minutes": market("KXBTCD-A", 0.45, 0.52, hours=0.99), "bid under 15 cents": market("KXBTCD-A", 0.13, 0.40, hours=0.6)}
        for name, row in rows.items():
            with self.subTest(name):
                self.assertEqual(self.run_seed(kalshi_ctx([row]))["intents"], [])

    def test_at_most_two_markets(self):
        rows = [market(f"KXBTCD-{n}", 0.45, 0.52, hours=0.6) for n in range(4)]
        out = self.run_seed(kalshi_ctx(rows))
        self.assertEqual(sorted({i["market"] for i in out["intents"]}), ["KXBTCD-0", "KXBTCD-1"])
        one_busy = self.run_seed(kalshi_ctx(rows, orders=[event_order("KXBTCD-9", "yes", 10, 0.4, ago(MON_1000, minutes=1))]))
        self.assertEqual({i["market"] for i in one_busy["intents"]}, {"KXBTCD-0"})

    def test_never_requotes_a_market_with_working_orders_or_a_full_pair(self):
        row = market("KXBTCD-A", 0.45, 0.52, hours=0.6)
        working = self.run_seed(kalshi_ctx([row], orders=[event_order("KXBTCD-A", "yes", 10, 0.46, ago(MON_1000, minutes=2))]))
        self.assertEqual((working["intents"], working["cancels"]), ([], []))
        pair = self.run_seed(kalshi_ctx([row], positions=[event_position("KXBTCD-A", "yes", 10, 0.46), event_position("KXBTCD-A", "no", 10, 0.49)]))
        self.assertEqual(pair["intents"], [])

    def test_completes_a_pair_only_on_the_missing_leg_and_only_at_a_locked_profit(self):
        held = [event_position("KXBTCD-A", "yes", 10, 0.46)]
        out = self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.44, 0.50, hours=0.5)], positions=held))
        self.assertEqual([(i["leg"], i["quantity"]) for i in out["intents"]], [("no", 10)])
        self.assertAlmostEqual(out["intents"][0]["limit_price"], 0.51)
        moved = self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.30, 0.36, hours=0.5)], positions=held))
        self.assertEqual(moved["intents"], [], "0.46 + 0.65 is over a dollar: no pair to lock")
        still_working = self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.44, 0.50, hours=0.5)], positions=held,
                                                 orders=[event_order("KXBTCD-A", "no", 10, 0.5, ago(MON_1000, minutes=1))]))
        self.assertEqual(still_working["intents"], [])

    def test_requotes_after_ten_minutes_by_cancelling_first(self):
        orders = [event_order("KXBTCD-A", "yes", 10, 0.46, ago(MON_1000, minutes=11), "ord-y"),
                  event_order("KXBTCD-A", "no", 10, 0.49, ago(MON_1000, minutes=11), "ord-n"),
                  event_order("KXBTCD-B", "yes", 10, 0.46, ago(MON_1000, minutes=9), "ord-fresh")]
        out = self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.45, 0.52, hours=0.6)], orders=orders))
        self.assertEqual(sorted(out["cancels"]), ["ord-n", "ord-y"])
        self.assertEqual(out["intents"], [])

    def test_sells_nothing_and_respects_cash(self):
        held = [event_position("KXBTCD-A", "yes", 10, 0.46), event_position("KXBTCD-A", "no", 10, 0.49)]
        self.assertEqual(self.sells(self.run_seed(kalshi_ctx([market("KXBTCD-A", 0.05, 0.12, hours=0.6)], positions=held))), [])
        poor = self.run_seed(kalshi_ctx([market("KXBTCD-B", 0.45, 0.52, hours=0.6)], cash=4.0))
        self.assertLessEqual(sum(i["quantity"] * i["limit_price"] for i in poor["intents"]), 3.92)
        self.assertEqual(self.run_seed(kalshi_ctx([market("KXBTCD-B", 0.45, 0.52, hours=0.6)], cash=1.0))["intents"], [])

    def test_the_header_says_it_is_a_control(self):
        self.assertIn("NO edge", load(self.SEED))
        self.assertIn("control", self.run_seed(kalshi_ctx([]))["thought"])


# --------------------------------------------------------------------------- crypto reversion
class CryptoReversionTests(SeedCase):
    SEED = "crypto-reversion"

    def ctx(self, last, now=MON_1100, **more):
        return alpaca_ctx(now, {"BTC/USD": make_bars(wiggle(40) + [last], more.pop("bars_end", now), 3600)}, **more)

    def test_buys_a_two_sigma_dip_with_a_market_order(self):
        out = self.run_seed(self.ctx(97.0))
        self.assertEqual(len(out["intents"]), 1)
        intent = out["intents"][0]
        self.assertEqual((intent["symbol"], intent["side"], intent["type"], intent["notional_usd"]), ("BTC/USD", "buy", "market", 40.0))
        self.assertIn("standard deviations", intent["reason"])

    def test_stays_out_without_a_dip_or_when_the_dip_cannot_pay_the_fees(self):
        self.assertEqual(self.run_seed(self.ctx(99.9))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(103.0))["intents"], [], "a spike is not a dip")
        shallow = alpaca_ctx(MON_1100, {"BTC/USD": make_bars(wiggle(40, amp=0.05) + [99.6], MON_1100, 3600)})
        self.assertEqual(self.run_seed(shallow)["intents"], [], "z is -8 but the mean is only 0.4% away: under the 1% gap")

    def test_stays_out_on_short_or_stale_bars(self):
        self.assertEqual(self.run_seed(alpaca_ctx(MON_1100, {"BTC/USD": make_bars(wiggle(10) + [90.0], MON_1100, 3600)}))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(97.0, bars_end=ago(MON_1100, hours=6)))["intents"], [])

    def test_never_double_enters(self):
        held = self.run_seed(self.ctx(97.0, positions=[position("BTC/USD", 0.4, 98.0, ago(MON_1100, hours=1))]))
        self.assertEqual(held["intents"], [])
        working = self.run_seed(self.ctx(97.0, orders=[order("BTC/USD", "buy", 0.4, 96.0, ago(MON_1100, minutes=5))]))
        self.assertEqual(working["intents"], [])

    def test_exits_at_the_mean(self):
        out = self.run_seed(self.ctx(100.1, positions=[position("BTC/USD", 0.412345678, 98.0, ago(MON_1100, hours=3))]))
        self.assertEqual([(i["side"], i["type"], i["quantity"]) for i in out["intents"]], [("sell", "market", 0.412345678)])
        self.assertIn("mean", out["intents"][0]["reason"])

    def test_exits_after_max_hold_hours(self):
        late = self.run_seed(self.ctx(99.8, positions=[position("BTC/USD", 0.4, 99.9, ago(MON_1100, hours=13))]))
        self.assertEqual(len(self.sells(late)), 1)
        self.assertIn("13.0 hours", late["intents"][0]["reason"])
        early = self.run_seed(self.ctx(99.8, positions=[position("BTC/USD", 0.4, 99.9, ago(MON_1100, hours=2))]))
        self.assertEqual(early["intents"], [])

    def test_exits_at_the_stop(self):
        out = self.run_seed(self.ctx(97.0, positions=[position("BTC/USD", 0.4, 100.5, ago(MON_1100, hours=1))]))
        self.assertEqual(len(self.sells(out)), 1)
        self.assertIn("stop", out["intents"][0]["reason"])

    def test_respects_cash_and_limits(self):
        self.assertEqual(self.run_seed(self.ctx(97.0, cash=20.0))["intents"][0]["notional_usd"], 19.6)
        self.assertEqual(self.run_seed(self.ctx(97.0, cash=0.9))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(97.0, limits={"max_position_usd": 100.0, "max_order_usd": 25.0}))["intents"][0]["notional_usd"], 25.0)
        self.assertEqual(self.run_seed(self.ctx(97.0, limits={"max_position_usd": 30.0, "max_order_usd": 75.0}))["intents"][0]["notional_usd"], 30.0)

    def test_three_dips_share_the_cash(self):
        bars = {s: make_bars(wiggle(40) + [97.0], MON_1100, 3600) for s in ("BTC/USD", "ETH/USD", "SOL/USD")}
        out = self.run_seed(alpaca_ctx(MON_1100, bars, cash=100.0))
        self.assertEqual([i["notional_usd"] for i in out["intents"]], [40.0, 40.0, 18.0])

    def test_mutated_params_are_used(self):
        self.assertEqual(self.run_seed(self.ctx(99.2, params={"z_entry": 2.0, "min_gap_pct": 0.5}))["intents"][0]["side"], "buy")
        self.assertEqual(self.run_seed(self.ctx(97.0, params={"z_entry": 20.0}))["intents"], [])


# ------------------------------------------------------------------------------- crypto trend
class CryptoTrendTests(SeedCase):
    SEED = "crypto-trend"

    def ctx(self, closes, **more):
        return alpaca_ctx(MON_1100, {"ETH/USD": make_bars(closes, MON_1100, 3600)}, **more)

    def test_buys_a_breakout_in_an_uptrend(self):
        out = self.run_seed(self.ctx(ramp(119, 100.0, 0.05) + [110.0]))
        self.assertEqual([(i["symbol"], i["side"], i["type"], i["notional_usd"]) for i in out["intents"]], [("ETH/USD", "buy", "market", 40.0)])
        self.assertIn("highest high", out["intents"][0]["reason"])

    def test_no_breakout_no_trade(self):
        self.assertEqual(self.run_seed(self.ctx(wiggle(120)))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(ramp(119, 100.0, 0.05) + [105.9]))["intents"], [], "inside the prior highs")

    def test_a_breakout_against_the_trend_filter_is_skipped(self):
        closes = ramp(119, 130.0, -0.25) + [116.0]   # a bounce over the 48-bar high inside a long decline
        self.assertGreater(closes[-1], max(closes[-49:-1]) * 1.001)
        self.assertLess(sum(closes[-24:]) / 24, sum(closes[-96:]) / 96)
        self.assertEqual(self.run_seed(self.ctx(closes))["intents"], [])

    def test_short_data_no_trade(self):
        self.assertEqual(self.run_seed(self.ctx(ramp(59, 100.0, 0.05) + [110.0]))["intents"], [])

    def test_never_double_enters(self):
        closes = ramp(119, 100.0, 0.05) + [110.0]
        self.assertEqual(self.run_seed(self.ctx(closes, positions=[position("ETH/USD", 0.3, 109.0, ago(MON_1100, hours=1))]))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(closes, orders=[order("ETH/USD", "buy", 0.3, 100.0, ago(MON_1100, minutes=1))]))["intents"], [])

    def test_exits_under_the_channel_low(self):
        out = self.run_seed(self.ctx(wiggle(119) + [98.0], positions=[position("ETH/USD", 0.3, 99.0, ago(MON_1100, hours=30))]))
        self.assertEqual([(i["side"], i["type"], i["quantity"]) for i in out["intents"]], [("sell", "market", 0.3)])
        self.assertIn("lowest low", out["intents"][0]["reason"])

    def test_exits_at_the_stop_and_otherwise_holds(self):
        stopped = self.run_seed(self.ctx(wiggle(120), positions=[position("ETH/USD", 0.3, 105.0, ago(MON_1100, hours=5))]))
        self.assertIn("stop", stopped["intents"][0]["reason"])
        holding = self.run_seed(self.ctx(wiggle(120), positions=[position("ETH/USD", 0.3, 100.0, ago(MON_1100, hours=5))]))
        self.assertEqual(holding["intents"], [])

    def test_respects_cash_and_limits(self):
        closes = ramp(119, 100.0, 0.05) + [110.0]
        self.assertEqual(self.run_seed(self.ctx(closes, cash=10.0))["intents"][0]["notional_usd"], 9.8)
        self.assertEqual(self.run_seed(self.ctx(closes, cash=1.0))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(closes, limits={"max_position_usd": 100.0, "max_order_usd": 15.0}))["intents"][0]["notional_usd"], 15.0)


# --------------------------------------------------------------------------- crypto dip limit
class CryptoDipLimitTests(SeedCase):
    SEED = "crypto-dip-limit"
    QUARTER = 900

    def ctx(self, closes=None, **more):
        return alpaca_ctx(MON_1100, {"SOL/USD": make_bars(closes or wiggle(64, amp=0.2), MON_1100, self.QUARTER)}, **more)

    def target(self):
        intent = self.run_seed(self.ctx())["intents"][0]
        return intent["limit_price"]

    def test_rests_one_limit_buy_under_the_market(self):
        out = self.run_seed(self.ctx())
        self.assertEqual(len(out["intents"]), 1)
        intent = out["intents"][0]
        self.assertEqual((intent["symbol"], intent["side"], intent["type"], intent["notional_usd"]), ("SOL/USD", "buy", "limit", 40.0))
        self.assertLess(intent["limit_price"], 99.2 + 1e-9, "at least 0.8% under the mean of 100")
        self.assertGreater(intent["limit_price"], 97.0)
        self.assertNotIn("post_only", intent)

    def test_keeps_a_resting_buy_that_is_still_near_the_target(self):
        out = self.run_seed(self.ctx(orders=[order("SOL/USD", "buy", 0.4, self.target(), ago(MON_1100, hours=3))]))
        self.assertEqual((out["intents"], out["cancels"]), ([], []))

    def test_moves_a_buy_by_cancelling_now_and_placing_next_wake(self):
        out = self.run_seed(self.ctx(orders=[order("SOL/USD", "buy", 0.4, self.target() * 0.97, ago(MON_1100, hours=3), "ord-far")]))
        self.assertEqual((out["intents"], out["cancels"]), ([], ["ord-far"]))

    def test_does_not_bid_at_or_over_the_market(self):
        out = self.run_seed(self.ctx(quotes={"SOL/USD": {"bid": 98.0, "ask": 98.1}}))
        self.assertEqual(out["intents"], [], "the dip price is over the bid: a limit there would take, not rest")

    def test_short_or_stale_bars_no_bid(self):
        self.assertEqual(self.run_seed(self.ctx(closes=wiggle(20)))["intents"], [])
        stale = alpaca_ctx(MON_1100, {"SOL/USD": make_bars(wiggle(64, amp=0.2), ago(MON_1100, hours=5), self.QUARTER)})
        self.assertEqual(self.run_seed(stale)["intents"], [])

    def test_holding_rests_a_limit_sell_at_the_mean(self):
        out = self.run_seed(self.ctx(positions=[position("SOL/USD", 0.404040404, 98.8, ago(MON_1100, hours=1))]))
        self.assertEqual(len(out["intents"]), 1)
        intent = out["intents"][0]
        self.assertEqual((intent["side"], intent["type"], intent["quantity"]), ("sell", "limit", 0.404040404))
        self.assertAlmostEqual(intent["limit_price"], 100.0, places=2)

    def test_holding_never_buys_more_and_cancels_a_leftover_buy(self):
        out = self.run_seed(self.ctx(positions=[position("SOL/USD", 0.4, 98.8, ago(MON_1100, hours=1))],
                                     orders=[order("SOL/USD", "buy", 0.2, 98.8, ago(MON_1100, hours=2), "ord-left"),
                                             order("SOL/USD", "sell", 0.4, 100.0, ago(MON_1100, hours=1), "ord-exit")]))
        self.assertEqual((self.buys(out), out["cancels"]), ([], ["ord-left"]))

    def test_moves_the_sell_by_cancelling_first(self):
        out = self.run_seed(self.ctx(positions=[position("SOL/USD", 0.4, 98.8, ago(MON_1100, hours=1))],
                                     orders=[order("SOL/USD", "sell", 0.4, 101.5, ago(MON_1100, hours=1), "ord-exit")]))
        self.assertEqual((out["intents"], out["cancels"]), ([], ["ord-exit"]))

    def test_stop_cancels_the_resting_sell_and_market_sells(self):
        out = self.run_seed(self.ctx(positions=[position("SOL/USD", 0.4, 104.0, ago(MON_1100, hours=1))],
                                     orders=[order("SOL/USD", "sell", 0.4, 100.0, ago(MON_1100, hours=1), "ord-exit")]))
        self.assertEqual(out["cancels"], ["ord-exit"])
        self.assertEqual([(i["side"], i["type"], i["quantity"]) for i in out["intents"]], [("sell", "market", 0.4)])
        self.assertIn("stop", out["intents"][0]["reason"])

    def test_time_limit_market_sells(self):
        out = self.run_seed(self.ctx(positions=[position("SOL/USD", 0.4, 100.0, ago(MON_1100, hours=25))]))
        self.assertEqual([(i["side"], i["type"]) for i in out["intents"]], [("sell", "market")])
        self.assertIn("25.0 hours", out["intents"][0]["reason"])

    def test_three_symbols_share_the_cash(self):
        bars = {s: make_bars(wiggle(64, amp=0.2), MON_1100, self.QUARTER) for s in ("BTC/USD", "ETH/USD", "SOL/USD")}
        out = self.run_seed(alpaca_ctx(MON_1100, bars, cash=100.0))
        self.assertEqual([i["notional_usd"] for i in out["intents"]], [40.0, 40.0, 18.0])
        self.assertEqual(self.run_seed(alpaca_ctx(MON_1100, bars, cash=0.5))["intents"], [])


# ------------------------------------------------------------------------------- crypto pairs
class CryptoPairsTests(SeedCase):
    SEED = "crypto-pairs"

    def ctx(self, last_ratio, **more):
        btc = wiggle(100, base=80000.0, amp=100.0)
        ratios = wiggle(99, base=0.05, amp=0.0002) + [last_ratio]
        eth = [b * r for b, r in zip(btc, ratios)]
        return alpaca_ctx(MON_1100, {"BTC/USD": make_bars(btc, MON_1100, 3600), "ETH/USD": make_bars(eth, MON_1100, 3600)}, **more)

    def test_buys_eth_when_eth_is_cheap_against_btc(self):
        out = self.run_seed(self.ctx(0.048))
        self.assertEqual([(i["symbol"], i["side"], i["type"], i["notional_usd"]) for i in out["intents"]], [("ETH/USD", "buy", "market", 50.0)])

    def test_buys_btc_when_btc_is_cheap_against_eth(self):
        out = self.run_seed(self.ctx(0.052))
        self.assertEqual([(i["symbol"], i["side"]) for i in out["intents"]], [("BTC/USD", "buy")])

    def test_stays_in_cash_when_the_ratio_is_ordinary_or_the_gap_is_too_small(self):
        self.assertEqual(self.run_seed(self.ctx(0.0501))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(0.04955))["intents"], [], "z is -2.25 but the ratio is only 0.9% from its mean: under the 1% gap")
        self.assertEqual(len(self.run_seed(self.ctx(0.04955, params={"min_gap_pct": 0.5}))["intents"]), 1)

    def test_unmatched_bars_no_trade(self):
        ctx = self.ctx(0.048)
        ctx["bars"]["ETH/USD"] = make_bars([4000.0] * 100, ago(MON_1100, minutes=30), 3600)  # half an hour off: no shared stamps
        self.assertEqual(self.run_seed(ctx)["intents"], [])

    def test_one_position_at_a_time(self):
        holding_btc = self.ctx(0.048, positions=[position("BTC/USD", 0.0006, 80000.0, ago(MON_1100, hours=9))])
        out = self.run_seed(holding_btc)
        self.assertEqual([(i["symbol"], i["side"]) for i in out["intents"]], [("BTC/USD", "sell")], "sell the old leg first; ETH waits for a later wake")
        working = self.run_seed(self.ctx(0.048, orders=[order("ETH/USD", "buy", 0.01, 3800.0, ago(MON_1100, minutes=2))]))
        self.assertEqual(working["intents"], [])

    def test_holds_eth_while_the_ratio_is_still_stretched(self):
        out = self.run_seed(self.ctx(0.0497, positions=[position("ETH/USD", 0.0125, 3980.0, ago(MON_1100, hours=9))]))
        self.assertEqual(out["intents"], [])

    def test_exits_to_cash_when_the_ratio_is_back(self):
        for ratio in (0.04995, 0.0508):
            with self.subTest(ratio=ratio):
                out = self.run_seed(self.ctx(ratio, positions=[position("ETH/USD", 0.0125, 3900.0, ago(MON_1100, hours=9))]))
                self.assertEqual([(i["side"], i["type"], i["quantity"]) for i in out["intents"]], [("sell", "market", 0.0125)])

    def test_exits_at_the_stop(self):
        out = self.run_seed(self.ctx(0.0497, positions=[position("ETH/USD", 0.0125, 4200.0, ago(MON_1100, hours=9))]))
        self.assertIn("stop", out["intents"][0]["reason"])

    def test_respects_cash_and_limits(self):
        self.assertEqual(self.run_seed(self.ctx(0.048, cash=30.0))["intents"][0]["notional_usd"], 29.4)
        self.assertEqual(self.run_seed(self.ctx(0.048, cash=0.2))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(0.048, limits={"max_position_usd": 20.0, "max_order_usd": 75.0}))["intents"][0]["notional_usd"], 20.0)


# --------------------------------------------------------------------------- equity overnight
def daily(closes, last_stamp=FRIDAY_BAR):
    return make_bars(closes, last_stamp, 86400)


class EquityOvernightTests(SeedCase):
    SEED = "equity-overnight"

    def ctx(self, now, closes=None, **more):
        closes = closes or ramp(30, 600.0, 1.0)
        return alpaca_ctx(now, {"SPY": daily(closes), "QQQ": daily(closes)}, **more)

    def test_buys_both_near_the_close_when_above_the_20_day_mean(self):
        out = self.run_seed(self.ctx(MON_1545))
        self.assertEqual([(i["symbol"], i["side"], i["type"], i["notional_usd"]) for i in out["intents"]],
                         [("SPY", "buy", "market", 50.0), ("QQQ", "buy", "market", 50.0)])
        self.assertIn("20-day mean", out["intents"][0]["reason"])

    def test_no_buy_under_the_mean_or_outside_the_window(self):
        self.assertEqual(self.run_seed(self.ctx(MON_1545, closes=ramp(30, 600.0, -1.0)))["intents"], [])
        for now in (MON_1000, MON_1100, "2026-09-21T19:30:00Z", "2026-09-21T19:59:30Z"):
            with self.subTest(now=now):
                self.assertEqual(self.run_seed(self.ctx(now))["intents"], [])

    def test_no_buy_on_short_or_stale_bars(self):
        self.assertEqual(self.run_seed(self.ctx(MON_1545, closes=ramp(10, 600.0, 1.0)))["intents"], [])
        stale = alpaca_ctx(MON_1545, {"SPY": daily(ramp(30, 600.0, 1.0), "2026-09-01T04:00:00Z")})
        self.assertEqual(self.run_seed(stale)["intents"], [])

    def test_sells_in_the_next_morning_window(self):
        held = [position("SPY", 0.081234567, 615.0, "2026-09-18T19:45:00Z")]
        out = self.run_seed(self.ctx(MON_0940, positions=held))
        self.assertEqual([(i["symbol"], i["side"], i["type"], i["quantity"]) for i in out["intents"]], [("SPY", "sell", "market", 0.081234567)])

    def test_a_missed_window_sells_late_but_todays_purchase_is_kept(self):
        old = self.run_seed(self.ctx(MON_1100, positions=[position("SPY", 0.08, 615.0, "2026-09-18T19:45:00Z")]))
        self.assertEqual(len(self.sells(old)), 1)
        self.assertIn("missed", old["intents"][0]["reason"])
        fresh = self.run_seed(self.ctx(MON_1555, positions=[position("SPY", 0.08, 629.0, MON_1545), position("QQQ", 0.08, 629.0, MON_1545)]))
        self.assertEqual(fresh["intents"], [], "bought ten minutes ago: neither sold nor bought again")

    def test_never_double_enters(self):
        out = self.run_seed(self.ctx(MON_1545, positions=[position("SPY", 0.08, 629.0, ago(MON_1545, minutes=4))],
                                     orders=[order("QQQ", "buy", 0.08, 629.0, ago(MON_1545, minutes=4))]))
        self.assertEqual(out["intents"], [])

    def test_never_trades_while_new_york_is_closed(self):
        held = [position("SPY", 0.08, 615.0, "2026-09-17T19:45:00Z")]
        for name, now in CLOSED.items():
            with self.subTest(name):
                self.assertEqual(self.run_seed(self.ctx(now))["intents"], [])
                self.assertEqual(self.run_seed(self.ctx(now, positions=held))["intents"], [])
        saturday_buy_window = "2026-09-19T19:45:00Z"
        self.assertEqual(self.run_seed(self.ctx(saturday_buy_window))["intents"], [])
        saturday_sell_window = "2026-09-19T13:40:00Z"
        self.assertEqual(self.run_seed(self.ctx(saturday_sell_window, positions=held))["intents"], [])

    def test_respects_cash_and_limits(self):
        first, second = [i["notional_usd"] for i in self.run_seed(self.ctx(MON_1545, cash=60.0))["intents"]]
        self.assertEqual(first, 50.0)
        self.assertTrue(8.79 <= second <= 8.8, "what is left of 98% of $60, floored to the cent")
        self.assertEqual(self.run_seed(self.ctx(MON_1545, cash=0.5))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(MON_1545, limits={"max_position_usd": 100.0, "max_order_usd": 20.0}))["intents"][0]["notional_usd"], 20.0)


# ------------------------------------------------------------------------------- equity trend
class EquityTrendTests(SeedCase):
    SEED = "equity-trend"
    STEPS = {"SPY": 0.5, "QQQ": 1.0, "IWM": 0.2, "TLT": -0.3, "GLD": 0.4}

    def ctx(self, now=MON_1100, steps=None, **more):
        bars = {s: daily(ramp(130, 300.0, step)) for s, step in (steps or self.STEPS).items()}
        return alpaca_ctx(now, bars, **more)

    def test_buys_the_leader_and_marks_the_day_done(self):
        out = self.run_seed(self.ctx())
        self.assertEqual([(i["symbol"], i["side"], i["type"], i["notional_usd"]) for i in out["intents"]], [("QQQ", "buy", "market", 75.0)])
        self.assertEqual(out["memory"], {"done": "2026-09-21"})
        self.assertIn("60-day return", out["intents"][0]["reason"])

    def test_cash_when_nothing_is_above_its_mean(self):
        out = self.run_seed(self.ctx(steps={s: -0.5 for s in self.STEPS}))
        self.assertEqual((out["intents"], out["memory"]), ([], {"done": "2026-09-21"}))

    def test_a_leader_under_its_own_mean_is_passed_over(self):
        # 400 for 35 days, a crash to 80 over the next 35, then a 60-day double to 160: the best 60-day return, still under its 100-day mean
        crash_and_bounce = [400.0] * 35 + [400.0 - 320.0 / 35 * (n + 1) for n in range(35)] + [80.0 + 80.0 / 60 * (n + 1) for n in range(60)]
        self.assertGreater(crash_and_bounce[-1] / crash_and_bounce[-61], 1.9)
        self.assertLess(crash_and_bounce[-1], sum(crash_and_bounce[-100:]) / 100)
        ctx = self.ctx()
        ctx["bars"]["IWM"] = daily(crash_and_bounce)
        self.assertEqual([i["symbol"] for i in self.run_seed(ctx)["intents"]], ["QQQ"])

    def test_rotation_sells_first_and_buys_on_the_following_wake(self):
        first = self.run_seed(self.ctx(positions=[position("SPY", 0.2, 350.0, "2026-09-01T15:00:00Z")]))
        self.assertEqual([(i["symbol"], i["side"], i["quantity"]) for i in first["intents"]], [("SPY", "sell", 0.2)])
        self.assertEqual(first["memory"], {}, "the day is not done until the buy")
        second = self.run_seed(self.ctx(now="2026-09-21T16:00:00Z", memory=first["memory"]))
        self.assertEqual([(i["symbol"], i["side"]) for i in second["intents"]], [("QQQ", "buy")])
        self.assertEqual(second["memory"], {"done": "2026-09-21"})

    def test_sells_to_cash_when_the_holding_loses_its_trend_and_nothing_leads(self):
        out = self.run_seed(self.ctx(steps={s: -0.5 for s in self.STEPS}, positions=[position("QQQ", 0.2, 350.0, "2026-09-01T15:00:00Z")]))
        self.assertEqual([(i["symbol"], i["side"]) for i in out["intents"]], [("QQQ", "sell")])

    def test_holding_the_leader_does_nothing(self):
        out = self.run_seed(self.ctx(positions=[position("QQQ", 0.2, 350.0, "2026-09-01T15:00:00Z")]))
        self.assertEqual((out["intents"], out["memory"]), ([], {"done": "2026-09-21"}))

    def test_acts_once_a_day(self):
        out = self.run_seed(self.ctx(memory={"done": "2026-09-21"}))
        self.assertEqual((out["intents"], out["memory"]), ([], {"done": "2026-09-21"}))
        tomorrow = self.run_seed(alpaca_ctx("2026-09-22T15:00:00Z", {s: daily(ramp(130, 300.0, step), "2026-09-22T04:00:00Z") for s, step in self.STEPS.items()},
                                            memory={"done": "2026-09-21"}))
        self.assertEqual(len(self.buys(tomorrow)), 1)

    def test_waits_for_a_working_order_and_for_enough_bars(self):
        self.assertEqual(self.run_seed(self.ctx(orders=[order("SPY", "sell", 0.2, 360.0, ago(MON_1100, minutes=3))]))["intents"], [])
        short = alpaca_ctx(MON_1100, {s: daily(ramp(50, 300.0, 1.0)) for s in self.STEPS})
        out = self.run_seed(short)
        self.assertEqual((out["intents"], out["memory"]), ([], {}))

    def test_only_between_1000_and_1530_new_york_on_a_trading_day(self):
        for name, now in {**CLOSED, "09:40": MON_0940, "15:45": MON_1545}.items():
            with self.subTest(name):
                self.assertEqual(self.run_seed(self.ctx(now=now))["intents"], [])
                held = self.run_seed(self.ctx(now=now, positions=[position("SPY", 0.2, 350.0, "2026-09-01T15:00:00Z")]))
                self.assertEqual(held["intents"], [])

    def test_respects_cash_and_limits(self):
        self.assertEqual(self.run_seed(self.ctx(cash=30.0))["intents"][0]["notional_usd"], 29.4)
        self.assertEqual(self.run_seed(self.ctx(cash=0.5))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(limits={"max_position_usd": 40.0, "max_order_usd": 75.0}))["intents"][0]["notional_usd"], 40.0)


# -------------------------------------------------------------------------------- equity rsi2
class EquityRsi2Tests(SeedCase):
    SEED = "equity-rsi2"
    UPTREND = [100.0 * 1.001 ** n for n in range(208)]

    def ctx(self, closes, now=MON_1100, **more):
        return alpaca_ctx(now, {"SPY": daily(closes)}, **more)

    def pullback(self):
        top = self.UPTREND[-1]
        return self.UPTREND + [top * 0.985, top * 0.97]

    def test_buys_a_two_day_pullback_in_an_uptrend(self):
        out = self.run_seed(self.ctx(self.pullback()))
        self.assertEqual([(i["symbol"], i["side"], i["type"], i["notional_usd"]) for i in out["intents"]], [("SPY", "buy", "market", 60.0)])
        self.assertIn("RSI(2)", out["intents"][0]["reason"])
        self.assertEqual(out["memory"], {"acted": {"SPY": "2026-09-21"}})

    def test_no_pullback_no_trade(self):
        self.assertEqual(self.run_seed(self.ctx(self.UPTREND + [self.UPTREND[-1] * 1.001] * 2))["intents"], [])

    def test_a_pullback_under_the_200_day_mean_is_skipped(self):
        downtrend = [200.0 * 0.999 ** n for n in range(208)]
        closes = downtrend + [downtrend[-1] * 0.985, downtrend[-1] * 0.97]
        self.assertEqual(self.run_seed(self.ctx(closes))["intents"], [])

    def test_needs_200_fresh_bars(self):
        self.assertEqual(self.run_seed(self.ctx(self.pullback()[-150:]))["intents"], [])
        stale = alpaca_ctx(MON_1100, {"SPY": daily(self.pullback(), "2026-09-08T04:00:00Z")})
        self.assertEqual(self.run_seed(stale)["intents"], [])

    def test_exits_on_a_close_above_the_5_day_mean(self):
        top = self.UPTREND[-1]
        closes = self.UPTREND + [top * 0.985, top * 0.97, top * 0.99]
        out = self.run_seed(self.ctx(closes, positions=[position("SPY", 0.095959595, top * 0.97, ago(MON_1100, days=3))]))
        self.assertEqual([(i["side"], i["type"], i["quantity"]) for i in out["intents"]], [("sell", "market", 0.095959595)])
        self.assertIn("5-day mean", out["intents"][0]["reason"])

    def test_exits_after_seven_trading_days(self):
        top = self.UPTREND[-1]
        sliding = self.UPTREND[:200] + [top * (1 - 0.004 * n) for n in range(1, 11)]   # never back over its 5-day mean
        old = self.run_seed(self.ctx(sliding, positions=[position("SPY", 0.1, top, ago(FRIDAY_BAR, days=7, hours=12))]))
        self.assertEqual(len(self.sells(old)), 1)
        self.assertIn("trading days", old["intents"][0]["reason"])
        young = self.run_seed(self.ctx(sliding, positions=[position("SPY", 0.1, top, ago(FRIDAY_BAR, days=2, hours=12))]))
        self.assertEqual(young["intents"], [])

    def test_never_double_enters_and_acts_once_a_day(self):
        held = self.run_seed(self.ctx(self.pullback(), positions=[position("SPY", 0.1, 120.0, ago(MON_1100, hours=1))]))
        self.assertEqual(self.buys(held), [])
        working = self.run_seed(self.ctx(self.pullback(), orders=[order("SPY", "buy", 1, 100.0, ago(MON_1100, minutes=1))]))
        self.assertEqual(working["intents"], [])
        again = self.run_seed(self.ctx(self.pullback(), memory={"acted": {"SPY": "2026-09-21"}}))
        self.assertEqual(again["intents"], [])
        next_day = self.run_seed(self.ctx(self.pullback(), memory={"acted": {"SPY": "2026-09-18"}}))
        self.assertEqual(len(self.buys(next_day)), 1)

    def test_never_trades_while_new_york_is_closed(self):
        top = self.UPTREND[-1]
        bounce = self.UPTREND + [top * 0.985, top * 0.97, top * 0.99]
        for name, now in CLOSED.items():
            with self.subTest(name):
                self.assertEqual(self.run_seed(self.ctx(self.pullback(), now=now))["intents"], [])
                self.assertEqual(self.run_seed(self.ctx(bounce, now=now, positions=[position("SPY", 0.1, top * 0.97, ago(now, days=3))]))["intents"], [])

    def test_respects_cash_and_limits(self):
        self.assertEqual(self.run_seed(self.ctx(self.pullback(), cash=50.0))["intents"][0]["notional_usd"], 49.0)
        self.assertEqual(self.run_seed(self.ctx(self.pullback(), cash=1.0))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(self.pullback(), limits={"max_position_usd": 100.0, "max_order_usd": 10.0}))["intents"][0]["notional_usd"], 10.0)


# -------------------------------------------------------------------------------- equity vwap
class EquityVwapTests(SeedCase):
    SEED = "equity-vwap"

    def session(self, now, last, flat=500.0, before=()):
        """5-minute bars from the 09:35 close up to `now`, flat at `flat`, the last close at `last`."""
        count = int((when(now) - when("2026-09-21T13:30:00Z")).total_seconds() // 300)
        return list(before) + make_bars([flat] * (count - 1) + [last], now, 300)

    def ctx(self, now=MON_1100, last=497.0, **more):
        return alpaca_ctx(now, {"QQQ": self.session(now, last, before=more.pop("before", ()))}, **more)

    def test_buys_a_stretch_under_vwap(self):
        out = self.run_seed(self.ctx())
        self.assertEqual([(i["symbol"], i["side"], i["type"], i["notional_usd"]) for i in out["intents"]], [("QQQ", "buy", "market", 50.0)])
        self.assertIn("VWAP", out["intents"][0]["reason"])

    def test_no_stretch_no_trade(self):
        self.assertEqual(self.run_seed(self.ctx(last=499.0))["intents"], [], "0.2% under VWAP is inside the band")
        self.assertEqual(self.run_seed(self.ctx(last=503.0))["intents"], [])

    def test_entries_only_between_1000_and_1500(self):
        self.assertEqual(self.run_seed(self.ctx(now="2026-09-21T13:55:00Z"))["intents"], [], "09:55: too early and too few bars")
        self.assertEqual(self.run_seed(self.ctx(now="2026-09-21T19:05:00Z"))["intents"], [], "15:05: too late to start a trade")
        self.assertEqual(len(self.run_seed(self.ctx(now="2026-09-21T18:55:00Z"))["intents"]), 1)

    def test_vwap_uses_todays_regular_session_only(self):
        premarket = make_bars([600.0] * 12, "2026-09-21T13:30:00Z", 300, volume=1e9)      # closes 08:35-09:30
        yesterday = make_bars([600.0] * 12, "2026-09-18T19:00:00Z", 300, volume=1e9)
        out = self.run_seed(self.ctx(last=499.5, before=yesterday + premarket))
        self.assertEqual(out["intents"], [], "with those bars in the VWAP, 499.5 would look 17% cheap")
        only_yesterday = alpaca_ctx(MON_1100, {"QQQ": make_bars([500.0] * 30 + [490.0], "2026-09-18T19:00:00Z", 300)})
        self.assertEqual(self.run_seed(only_yesterday)["intents"], [])

    def test_stale_session_bars_no_entry(self):
        ctx = alpaca_ctx(MON_1100, {"QQQ": self.session("2026-09-21T14:30:00Z", 497.0)})
        self.assertEqual(self.run_seed(ctx)["intents"], [])

    def test_exits_at_vwap(self):
        out = self.run_seed(self.ctx(last=500.5, positions=[position("QQQ", 0.100603621, 497.0, ago(MON_1100, minutes=30))]))
        self.assertEqual([(i["side"], i["type"], i["quantity"]) for i in out["intents"]], [("sell", "market", 0.100603621)])
        self.assertIn("VWAP", out["intents"][0]["reason"])
        holding = self.run_seed(self.ctx(last=498.0, positions=[position("QQQ", 0.1, 497.0, ago(MON_1100, minutes=30))]))
        self.assertEqual(holding["intents"], [])

    def test_stop_sells_and_blocks_reentry_for_the_day(self):
        out = self.run_seed(self.ctx(last=494.0, positions=[position("QQQ", 0.1, 497.0, ago(MON_1100, minutes=30))]))
        self.assertIn("stop", out["intents"][0]["reason"])
        self.assertEqual(out["memory"], {"stopped": {"QQQ": "2026-09-21"}})
        later = self.run_seed(self.ctx(now="2026-09-21T16:00:00Z", last=494.0, memory=out["memory"]))
        self.assertEqual(later["intents"], [], "stopped once today: left alone")
        self.assertEqual(later["memory"], out["memory"])
        tomorrow = self.run_seed(self.ctx(memory={"stopped": {"QQQ": "2026-09-18"}}))
        self.assertEqual(len(self.buys(tomorrow)), 1)

    def test_flat_by_1550_and_never_overnight(self):
        late = self.run_seed(self.ctx(now="2026-09-21T19:50:00Z", last=498.0, positions=[position("QQQ", 0.1, 497.5, "2026-09-21T18:00:00Z")]))
        self.assertEqual(len(self.sells(late)), 1)
        self.assertIn("15:50", late["intents"][0]["reason"])
        carried = alpaca_ctx(MON_0940, {"QQQ": []}, positions=[position("QQQ", 0.1, 497.5, "2026-09-18T18:00:00Z")])
        out = self.run_seed(carried)
        self.assertEqual([(i["side"], i["quantity"]) for i in out["intents"]], [("sell", 0.1)])
        self.assertIn("overnight", out["intents"][0]["reason"])

    def test_never_double_enters(self):
        self.assertEqual(self.buys(self.run_seed(self.ctx(positions=[position("QQQ", 0.1, 497.2, ago(MON_1100, minutes=5))]))), [])
        self.assertEqual(self.run_seed(self.ctx(orders=[order("QQQ", "buy", 1, 490.0, ago(MON_1100, minutes=5))]))["intents"], [])

    def test_never_trades_while_new_york_is_closed(self):
        for name, now in CLOSED.items():
            with self.subTest(name):
                bars = {"QQQ": make_bars([500.0] * 20 + [490.0], now, 300)}
                self.assertEqual(self.run_seed(alpaca_ctx(now, bars))["intents"], [])
                held = alpaca_ctx(now, bars, positions=[position("QQQ", 0.1, 520.0, ago(now, days=1))])
                self.assertEqual(self.run_seed(held)["intents"], [])

    def test_respects_cash_and_limits(self):
        self.assertEqual(self.run_seed(self.ctx(cash=20.0))["intents"][0]["notional_usd"], 19.6)
        self.assertEqual(self.run_seed(self.ctx(cash=0.3))["intents"], [])
        self.assertEqual(self.run_seed(self.ctx(limits={"max_position_usd": 12.0, "max_order_usd": 75.0}))["intents"][0]["notional_usd"], 12.0)


# ------------------------------------------------------------------- the seeds in the simulator
class ReplayTests(unittest.TestCase):
    """Each venue once through `league.replay`: the orders a seed sends are accepted and filled
    by the same simulator that will score it, with nothing refused."""

    def replay(self, name, tape):
        from league.replay import run_replay

        result = run_replay(load(name), None, tape)
        self.assertTrue(result.get("ok"), result.get("error"))
        self.assertEqual(result["errors"], 0, result.get("last_error"))
        self.assertEqual(result["refused"], 0, result.get("refusal_reasons"))
        return result

    def test_favorites_maker_rests_fills_and_settles(self):
        close = "2026-09-21T17:00:00Z"
        steps = []
        for index in range(12):
            row = {"market": "KXBTCD-26SEP2113-T80000", "series": "KXBTCD", "title": "BTC above 80000", "yes_bid": 0.93, "yes_ask": 0.95,
                   "close_time": close, "volume_24h": 8000, "open_interest": 900, "strike": 80000.0}
            if index == 3:
                row["yes_ask_low"] = 0.92   # the ask traded down through the resting 0.93 bid
            steps.append({"t": iso(when(MON_1000) + timedelta(minutes=10 * index)), "markets": [row]})
        steps.append({"t": "2026-09-21T17:10:00Z", "markets": []})
        tape = {"venue": "kalshi", "horizon": "hour", "step_seconds": 600, "steps": steps, "results": {"KXBTCD-26SEP2113-T80000": "yes"}}
        result = self.replay("favorites-maker", tape)
        self.assertEqual((result["fills"], result["maker_fills"]), (1, 1))
        self.assertAlmostEqual(result["final_equity"], 200.0 + 10 * 0.07, places=6)

    def test_crypto_reversion_buys_the_dip_and_sells_the_mean(self):
        closes = wiggle(40) + [97.0, 98.5, 100.2, 100.0]
        bars = make_bars(closes, "2026-09-22T00:00:00Z", 3600)
        tape = {"venue": "alpaca", "horizon": "hour", "step_seconds": 3600, "half_spread_bps": 2.0,
                "steps": [{"t": b["t"], "bars": {"BTC/USD": {k: b[k] for k in "ohlcv"}}} for b in bars]}
        result = self.replay("crypto-reversion", tape)
        self.assertEqual((result["fills"], result["trades"], result["open_positions"]), (2, 1, 0))
        self.assertGreater(result["final_equity"], 200.0)

    def test_crypto_dip_limit_is_a_maker_on_both_sides(self):
        closes = wiggle(64, amp=0.2) + [99.5, 99.6, 100.3, 100.2]   # a dip that stays under the mean, then a push through it
        bars = make_bars(closes, "2026-09-22T00:00:00Z", 900)
        bars[64]["l"] = 98.0    # a wick through the resting dip bid
        tape = {"venue": "alpaca", "horizon": "hour", "step_seconds": 900, "half_spread_bps": 2.0,
                "steps": [{"t": b["t"], "bars": {"SOL/USD": {k: b[k] for k in "ohlcv"}}} for b in bars]}
        result = self.replay("crypto-dip-limit", tape)
        self.assertEqual((result["fills"], result["maker_fills"], result["trades"]), (2, 2, 1))
        self.assertGreater(result["final_equity"], 200.0)

    def test_equity_vwap_trades_inside_the_session(self):
        closes = [500.0] * 17 + [497.0, 498.5, 500.5, 500.4]
        bars = make_bars(closes, "2026-09-21T15:15:00Z", 300)
        tape = {"venue": "alpaca", "horizon": "hour", "step_seconds": 300, "half_spread_bps": 1.0,
                "steps": [{"t": b["t"], "bars": {"QQQ": {k: b[k] for k in "ohlcv"}}} for b in bars]}
        result = self.replay("equity-vwap", tape)
        self.assertEqual((result["fills"], result["trades"], result["open_positions"]), (2, 1, 0))
        self.assertGreater(result["final_equity"], 200.0)

    def test_daily_equity_seeds_send_nothing_on_a_tape_stamped_at_midnight_new_york(self):
        """A 1Day bar is stamped with its close, midnight New York, when the market is shut. The
        daily seeds obey the clock in replay as they would live, so such a tape shows them flat:
        they need steps inside the session to be scored at rung 0."""
        closes = [100.0 * 1.001 ** n for n in range(230)]
        closes += [closes[-1] * 0.985, closes[-1] * 0.97, closes[-1] * 0.99, closes[-1] * 1.0]
        bars = make_bars(closes, "2026-09-19T04:00:00Z", 86400)
        tape = {"venue": "alpaca", "horizon": "day", "step_seconds": 86400, "half_spread_bps": 1.0,
                "steps": [{"t": b["t"], "bars": {s: {k: b[k] for k in "ohlcv"} for s in ("SPY", "QQQ", "IWM", "TLT", "GLD")}} for b in bars]}
        for name in ("equity-overnight", "equity-trend", "equity-rsi2"):
            with self.subTest(name):
                self.assertEqual(self.replay(name, tape)["fills"], 0)


if __name__ == "__main__":
    unittest.main()
