"""Historical replay of the long-calls-and-puts desk, and the options-derived features.

Built Sept 22, 2026. Alpaca has option trade BARS since 2024-01-18 and no historical option
QUOTES at all (measured through the gateway), so every bid and ask in an options replay is an
estimate from prints. These tests pin the conservative execution rules that estimate is wrapped
in: point-in-time listing, the 100 multiplier and fees, no fill without prints, a touched limit
is not a fill, the expiry rule, and no lookahead in the features.
"""

import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from league import options_history as oh
from league.replay import run_replay

STRATEGY = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "style": "test", "asset_class": "option", "symbols": ["F"],
         "bars": {"timeframe": "1Day", "limit": 5}, "max_days_to_expiry": 28}
PARAMS = {"occ": "", "buy_at": "", "limit": 0.0, "sell_at": "", "sell_limit": 0.0, "qty": 1}

def decide(ctx):
    p = ctx["params"]
    out = []
    if ctx["now"] == p["buy_at"]:
        out.append({"occ": p["occ"], "side": "buy", "quantity": p["qty"], "type": "limit", "limit_price": p["limit"], "reason": "test entry"})
    if ctx["now"] == p["sell_at"]:
        out.append({"occ": p["occ"], "side": "sell", "quantity": p["qty"], "type": "limit", "limit_price": p["sell_limit"], "reason": "test exit"})
    seen = [r["occ"] for r in ctx.get("chain") or []]
    return {"intents": out, "memory": {"chain": seen}}
'''

C1 = "F260306C00010000"  # expires Friday March 6, 2026
C2 = "F260313C00010500"  # first prints later
OLD = "F260227C00010000"  # expired the week before
LIMITS = {"max_position_usd": 100.0, "max_order_usd": 75.0}


def bar(o, h, l, c, v=50.0, n=10):
    return {"o": o, "h": h, "l": l, "c": c, "v": v, "n": n}


def tape(steps, contracts=None):
    return {"venue": "alpaca", "asset_class": "option", "horizon": "day", "symbols": ["F"], "steps": steps,
            "contracts": contracts or {C1: {"underlying": "F", "expiry": "2026-03-06", "strike": 10.0, "right": "call", "first_print": "2026-03-02T15:00:00Z"},
                                       C2: {"underlying": "F", "expiry": "2026-03-13", "strike": 10.5, "right": "call", "first_print": "2026-03-02T15:15:00Z"},
                                       OLD: {"underlying": "F", "expiry": "2026-02-27", "strike": 10.0, "right": "call", "first_print": "2026-02-20T15:00:00Z"}},
            "chain_rules": {"max_days_to_expiry": 28, "moneyness": 0.2, "per_underlying": 40},
            "spread_model": dict(oh.SPREAD_MODEL), "liquidity": dict(oh.LIQUIDITY), "fee_per_contract_usd": 0.05, "multiplier": 100,
            "warmup_bars": {}, "half_spread_bps": 1.0}


def step(t, options=None, spot=10.0):
    return {"t": t, "bars": {}, "execution_bars": {"F": bar(spot, spot, spot, spot, 1000)}, "options": options or {}}


def run(steps, **params):
    result = run_replay(STRATEGY, params, tape(steps), stake=1000.0, limits=LIMITS, audit=True)
    assert result["ok"], result
    return result


class Execution(unittest.TestCase):
    def test_one_contract_costs_a_hundred_times_its_premium_plus_the_fee(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                      step("2026-03-02T15:15:00Z", {C1: bar(0.40, 0.41, 0.39, 0.40)})],
                     occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.40)
        self.assertEqual([(f["side"], f["price"], f["quantity"], f["fee"]) for f in result["fill_log"]], [("buy", 0.40, 1.0, 0.05)])
        self.assertAlmostEqual(result["fees_usd"], 0.05)
        # marked at the SHOWN bid: the last print 0.40 less max($0.01, 4.5% of it)
        self.assertAlmostEqual(result["final_equity"], 1000 - 40.05 + (0.40 - 0.018) * 100, places=6)

    def test_nothing_fills_in_the_bar_the_decision_saw(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.30, 0.40)})], occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.45)
        self.assertEqual(result["fills"], 0)
        self.assertEqual(result["open_orders"], 1)

    def test_a_touched_limit_is_not_a_fill(self):
        touched = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                       step("2026-03-02T15:15:00Z", {C1: bar(0.41, 0.42, 0.39, 0.41)})],
                      occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.39)
        self.assertEqual(touched["fills"], 0)
        through = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                       step("2026-03-02T15:15:00Z", {C1: bar(0.41, 0.42, 0.38, 0.41)})],
                      occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.39)
        self.assertEqual([f["price"] for f in through["fill_log"]], [0.39])

    def test_no_fill_without_prints_and_a_day_order_expires(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                      step("2026-03-02T16:00:00Z"), step("2026-03-02T21:00:00Z")],
                     occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.44)
        self.assertEqual((result["fills"], result["expired_orders"], result["open_orders"]), (0, 1, 0))

    def test_a_day_order_cannot_fill_after_the_close(self):
        """Found in review: an order working at the bell met the next morning's first bar."""
        overnight = run([step("2026-03-02T20:45:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),   # 15:45 New York
                         step("2026-03-03T14:45:00Z", {C1: bar(0.40, 0.41, 0.30, 0.40)})],  # 09:45 the next day, trading through
                        occ=C1, buy_at="2026-03-02T20:45:00Z", limit=0.40)
        self.assertEqual((overnight["fills"], overnight["expired_orders"]), (0, 1))
        last_bar = run([step("2026-03-02T20:45:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                        step("2026-03-02T21:00:00Z", {C1: bar(0.40, 0.41, 0.30, 0.40)})],  # the 15:45-16:00 bar: still the order's day
                       occ=C1, buy_at="2026-03-02T20:45:00Z", limit=0.40)
        self.assertEqual(last_bar["fills"], 1)

    def test_a_tape_of_another_timeframe_is_refused(self):
        wrong = tape([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)})])
        wrong["timeframe"] = "1Hour"
        result = run_replay(STRATEGY, {}, wrong, stake=1000.0, limits=LIMITS)
        self.assertEqual(result["error"], "unsupported input: tape timeframe does not match declared bars")

    def test_a_thin_bar_does_not_fill_beyond_its_volume(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                      step("2026-03-02T15:15:00Z", {C1: bar(0.40, 0.41, 0.30, 0.40, v=6, n=3)})],
                     occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.40)
        self.assertEqual(result["fills"], 0)  # one contract is more than 10% of six
        self.assertEqual(result["options"]["liquidity_misses"], 1)

    def test_the_quote_shown_is_the_central_estimate_and_a_fill_pays_the_wider_one(self):
        code = STRATEGY.replace('seen = [r["occ"] for r in ctx.get("chain") or []]', 'seen = [[r["bid"], r["ask"]] for r in ctx.get("chain") or []]')
        steps = [step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.48, 0.32, 0.40)}),  # a wide bar: the range says 0.08 either side
                 step("2026-03-02T15:15:00Z", {C1: bar(0.40, 0.41, 0.40, 0.40)})]
        result = run_replay(code, {"occ": C1, "buy_at": "2026-03-02T15:00:00Z", "limit": 0.50}, tape(steps), stake=1000.0, limits=LIMITS, audit=True)
        self.assertEqual(result["final_memory"]["chain"], [[0.382, 0.418]])  # shown: 0.40 +- 4.5%
        self.assertEqual([f["price"] for f in result["fill_log"]], [0.48])  # paid: the open 0.40 + half the 0.16 range

    def test_an_order_at_the_shown_touch_is_marketable_and_never_fills_past_its_limit(self):
        """A sell at the bid a strategy is shown fills at once live; so it must here, at that
        bid or worse, never better (found when a stop at the shown bid kept missing a falling market)."""
        steps = [step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                 step("2026-03-02T15:15:00Z", {C1: bar(0.40, 0.41, 0.39, 0.40)}),
                 step("2026-03-02T15:30:00Z", {C1: bar(0.40, 0.40, 0.40, 0.40)}),
                 step("2026-03-02T15:45:00Z", {C1: bar(0.40, 0.40, 0.40, 0.40)})]
        result = run(steps, occ=C1, buy_at="2026-03-02T15:15:00Z", limit=0.418, sell_at="2026-03-02T15:30:00Z", sell_limit=0.382)
        self.assertEqual([(f["side"], f["price"]) for f in result["fill_log"]], [("buy", 0.418), ("sell", 0.382)])  # the limits: the conservative touch is worse

    def test_the_execution_stress_changes_what_a_fill_pays_not_the_quote_shown(self):
        steps = [step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                 step("2026-03-02T15:15:00Z", {C1: bar(0.40, 0.41, 0.40, 0.40)})]
        base = run_replay(STRATEGY, {"occ": C1, "buy_at": "2026-03-02T15:00:00Z", "limit": 0.45}, tape(steps), stake=1000.0, limits=LIMITS, audit=True)
        stressed_tape = tape(steps)
        stressed_tape["spread_model"]["stress"] = 2.0
        stressed = run_replay(STRATEGY, {"occ": C1, "buy_at": "2026-03-02T15:00:00Z", "limit": 0.45}, stressed_tape, stake=1000.0, limits=LIMITS, audit=True)
        self.assertEqual([f["price"] for f in base["fill_log"]], [0.42])  # the open 0.40 plus the estimated half 0.02
        self.assertEqual([f["price"] for f in stressed["fill_log"]], [0.44])  # twice the half, and still under the limit
        self.assertEqual(base["final_memory"], stressed["final_memory"])  # the same chain was shown

    def test_market_orders_and_plain_tickers_are_refused(self):
        code = STRATEGY.replace('"type": "limit", "limit_price": p["limit"]', '"type": "market"')
        result = run_replay(code, {"occ": C1, "buy_at": "2026-03-02T15:00:00Z"}, tape([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)})]),
                            stake=1000.0, limits=LIMITS)
        self.assertEqual(result["refusal_reasons"], {"an option order must be a limit order": 1})
        stock = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)})], occ="F", buy_at="2026-03-02T15:00:00Z", limit=10.0)
        self.assertEqual(list(stock["refusal_reasons"]), ["this specialty trades options only: name the contract's OCC code"])

    def test_the_order_cap_counts_the_multiplier(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.80, 0.82, 0.78, 0.80)})], occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.80)
        self.assertEqual(result["refusal_reasons"], {"over the order cap": 1})  # $80 against $75


class Underlier(unittest.TestCase):
    def test_the_underlier_is_read_unadjusted_and_close_stamped(self):
        """Found in review: `adjustment=all` history is adjusted for dividends paid after each
        bar, which option strikes never are."""
        from league.tapes import AlpacaData

        asked = []

        class Client:
            def request(self, method, url, headers=None, body=None, what=""):
                asked.append(url)
                page = "page_token=" in url
                rows = [{"t": "2026-03-02T15:00:00Z", "o": 10, "h": 10.2, "l": 9.9, "c": 10.1, "v": 5}] if not page else \
                       [{"t": "2026-03-02T15:15:00Z", "o": 10.1, "h": 10.3, "l": 10.0, "c": 10.2, "v": 6}]
                return 200, {"bars": {"F": rows}, "next_page_token": None if page else "next"}

        data = AlpacaData(Client(), feed="sip", clock=lambda: datetime(2026, 3, 3, tzinfo=timezone.utc).timestamp())
        bars = oh.adapter_from(data)("F", "15Min", "2026-03-02T00:00:00Z", "2026-03-03T00:00:00Z")
        self.assertTrue(all("adjustment=raw" in url and "feed=sip" in url for url in asked))
        self.assertEqual([b["t"] for b in bars], ["2026-03-02T15:15:00Z", "2026-03-02T15:30:00Z"])  # stamped at the close, both pages


class Retries(unittest.TestCase):
    def test_a_timed_out_read_is_asked_again_and_a_refusal_is_not(self):
        tries = []

        def flaky():
            tries.append(1)
            if len(tries) < 3:
                raise TimeoutError("The read operation timed out")
            return "ok"

        self.assertEqual(oh._retrying(flaky, pause=0), "ok")
        self.assertEqual(len(tries), 3)
        refused = []

        def refuse():
            refused.append(1)
            raise oh.HistoryError("HTTP 403 Not a path this gateway signs.")

        with self.assertRaises(oh.HistoryError):
            oh._retrying(refuse, pause=0)
        self.assertEqual(len(refused), 1)


class RecordedQuotes(unittest.TestCase):
    """From Sept 22, 2026 the House keeps the OPRA quotes it reads for live chains. Where a tape
    has one, the replay uses it instead of an estimate."""

    def test_a_recorded_quote_after_the_order_fills_one_contract_at_its_ask(self):
        first = step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)})
        later = {**step("2026-03-02T15:15:00Z"), "quotes": {C1: {"t": "2026-03-02T15:07:00Z", "bid": 0.39, "ask": 0.41}}}
        result = run([first, later], occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.41)
        self.assertEqual([(f["price"], f["how"]) for f in result["fill_log"]], [(0.41, "recorded quote")])
        self.assertEqual(result["options"]["recorded_quote_fills"], 1)

    def test_a_recorded_ask_above_the_limit_does_not_fill_and_the_chain_says_where_its_quote_came_from(self):
        first = step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)})
        later = {**step("2026-03-02T15:15:00Z"), "quotes": {C1: {"t": "2026-03-02T15:10:00Z", "bid": 0.40, "ask": 0.43}}}
        code = STRATEGY.replace('seen = [r["occ"] for r in ctx.get("chain") or []]', 'seen = [[r["occ"], r["bid"], r["ask"], r["quote_source"]] for r in ctx.get("chain") or []]')
        result = run_replay(code, {"occ": C1, "buy_at": "2026-03-02T15:00:00Z", "limit": 0.41}, tape([first, later]), stake=1000.0, limits=LIMITS, audit=True)
        self.assertEqual(result["fills"], 0)
        self.assertEqual(result["final_memory"]["chain"], [[C1, 0.40, 0.43, "recorded OPRA quote"]])

    def test_the_estimate_is_measured_against_recorded_quotes(self):
        with tempfile.TemporaryDirectory() as root:
            store = oh.OptionsHistory(Path(root) / "c.sqlite")
            self.addCleanup(store.close)
            store.db.execute("INSERT INTO bars VALUES (?, '15Min', '2026-09-22T14:00:00Z', 0.40, 0.42, 0.38, 0.40, 50, 10, 0.4)", (C1,))
            store.db.commit()
            store.record_quotes([{"symbol": C1, "bid": 0.39, "ask": 0.41, "as_of": "2026-09-22T14:05:00Z"},   # half 0.01: the estimate (0.02) is wider
                                 {"symbol": C1, "bid": 0.35, "ask": 0.45, "as_of": "2026-09-22T14:10:00Z"},   # half 0.05: it is not
                                 {"symbol": C1, "bid": 0.30, "ask": 0.50, "as_of": "2026-09-22T13:55:00Z"}],  # before any print: not compared
                                source="opra")
            self.assertEqual(store.spread_check(), {"quotes_compared": 2, "estimate_at_least_as_wide": 1, "share_conservative": 0.5,
                                                    "display_share_wider": 0.5})

    def test_only_opra_quotes_are_kept(self):
        with tempfile.TemporaryDirectory() as root:
            store = oh.OptionsHistory(Path(root) / "q.sqlite")
            self.addCleanup(store.close)
            row = {"symbol": C1, "bid": 0.40, "ask": 0.42, "as_of": "2026-09-22T14:00:01.5Z"}
            self.assertEqual(store.record_quotes([row], source="indicative"), 0)
            self.assertEqual(store.record_quotes([row, {**row, "bid": 0.0}], source="opra"), 1)
            self.assertEqual(store.quotes([C1]), {C1: [{"t": "2026-09-22T14:00:01Z", "bid": 0.40, "ask": 0.42}]})


class PointInTime(unittest.TestCase):
    def test_a_contract_that_has_not_printed_yet_is_not_listed(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                      step("2026-03-02T15:15:00Z", {C2: bar(0.30, 0.31, 0.29, 0.30)})],
                     occ=C2, buy_at="2026-03-02T15:00:00Z", limit=0.30)
        self.assertEqual(list(result["refusal_reasons"]), ["not listed at this step: the contract had not printed yet (point-in-time)"])
        self.assertEqual(result["final_memory"]["chain"], [C1, C2])  # shown once it printed

    def test_an_expired_contract_and_one_expiring_today_cannot_be_entered(self):
        result = run([step("2026-03-02T15:00:00Z", {OLD: bar(0.40, 0.42, 0.38, 0.40)})], occ=OLD, buy_at="2026-03-02T15:00:00Z", limit=0.40)
        self.assertEqual(list(result["refusal_reasons"]), ["an option entry must expire after today"])
        today = run([step("2026-03-06T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)})], occ=C1, buy_at="2026-03-06T15:00:00Z", limit=0.40)
        self.assertEqual(list(today["refusal_reasons"]), ["an option entry must expire after today"])

    def test_a_stale_print_is_no_quote(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}), step("2026-03-02T16:00:00Z")],
                     occ=C1, buy_at="2026-03-02T16:00:00Z", limit=0.40)
        self.assertEqual(list(result["refusal_reasons"]), ["no quote for this contract at this step: no qualifying print within the quote age"])


class Expiry(unittest.TestCase):
    def test_a_held_contract_is_offered_on_its_last_afternoon_and_written_off_if_unsold(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                      step("2026-03-02T15:15:00Z", {C1: bar(0.40, 0.41, 0.38, 0.40)}),
                      step("2026-03-06T19:30:00Z", {C1: bar(0.10, 0.10, 0.10, 0.10)}),  # 14:30 New York
                      step("2026-03-06T21:00:00Z")],  # the bell, and no print since
                     occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.40)
        self.assertEqual(result["options"]["forced_expiry_offers"], 1)
        self.assertEqual(result["options"]["written_off_at_expiry"], 1)
        self.assertEqual(result["digest"]["worst"][0]["how"], "expired: written off at zero")
        self.assertAlmostEqual(result["final_equity"], 1000 - 40.05, places=6)

    def test_the_expiry_offer_fills_on_a_later_print(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                      step("2026-03-02T15:15:00Z", {C1: bar(0.40, 0.41, 0.38, 0.40)}),
                      step("2026-03-06T19:30:00Z", {C1: bar(0.60, 0.60, 0.60, 0.60)}),
                      step("2026-03-06T19:45:00Z", {C1: bar(0.62, 0.70, 0.60, 0.65)})],
                     occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.40)
        sells = [f for f in result["fill_log"] if f["side"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0]["how"], "expiry rule")
        self.assertEqual(result["open_positions"], 0)


class BlackScholes(unittest.TestCase):
    def test_implied_volatility_round_trips_a_synthetic_price(self):
        for right in ("call", "put"):
            for strike in (90.0, 100.0, 108.0):
                for vol in (0.12, 0.35, 0.9):
                    price = oh.bs_price(100.0, strike, 30 / 365, vol, right)
                    self.assertAlmostEqual(oh.implied_vol(price, 100.0, strike, 30 / 365, right), vol, places=5)

    def test_a_price_no_volatility_explains_is_none_not_a_number(self):
        self.assertIsNone(oh.implied_vol(0.5, 100.0, 90.0, 30 / 365, "call"))  # under intrinsic
        self.assertIsNone(oh.implied_vol(0.0, 100.0, 100.0, 30 / 365, "call"))


def _daily(day, close):
    """An underlier daily bar close-stamped at the NY midnight after its session."""
    return {"t": oh.close_stamp(f"{day}T05:00:00Z", "1Day"), "o": close, "h": close * 1.01, "l": close * 0.99, "c": close, "v": 1e6}


class FakeVenue:
    """The two endpoints ingestion reads, priced with Black-Scholes at 25% volatility."""

    def __init__(self, days, fail_once=None, fail_bars=False):
        self.days, self.calls, self.fail_once, self.fail_bars = days, [], set(fail_once or ()), fail_bars

    def get(self, path, params):
        self.calls.append((path, dict(params)))
        if path == "/v2/options/contracts":
            if params["status"] != "inactive":
                return {"option_contracts": []}
            rows = []
            for expiry in ("2026-03-13", "2026-03-20"):
                for strike in (90, 95, 100, 105, 110):
                    for right in "CP":
                        rows.append({"symbol": f"SPY{expiry[2:4]}{expiry[5:7]}{expiry[8:]}{right}{strike * 1000:08d}", "size": "100", "status": "inactive"})
            return {"option_contracts": rows}
        if path == "/v1beta1/options/trades":
            raise oh.HistoryError("HTTP 403 Not a path this gateway signs.")
        symbols = params["symbols"].split(",")
        if self.fail_bars:
            raise oh.HistoryError("HTTP 429 too many requests")
        if any(s[3:9] in self.fail_once for s in symbols):
            self.fail_once.clear()
            raise oh.HistoryError("HTTP 503 upstream")
        out = {}
        for occ in symbols:
            info = oh.parse_occ(occ)
            rows = []
            for day in self.days:
                if day > info["expiry"] or not params["start"][:10] <= day <= params["end"][:10]:
                    continue
                years = oh.years_to(info["expiry"], datetime.fromisoformat(day + "T21:00:00+00:00").timestamp())
                price = round(oh.bs_price(100.0, info["strike"], years, 0.25, info["right"]), 4)
                if price > 0.01 and params["timeframe"] == "1Day":
                    rows.append({"t": f"{day}T05:00:00Z", "o": price, "h": price, "l": price, "c": price, "v": 100, "n": 20, "vw": price})
                elif price > 0.01:  # two 15-minute bars a day, 11:00 and 11:15 New York
                    for minute, move in (("15:00", 0.0), ("15:15", -0.02)):
                        p = max(0.01, round(price + move, 2))
                        rows.append({"t": f"{day}T{minute}:00Z", "o": p, "h": p + 0.01, "l": p - 0.01, "c": p, "v": 100, "n": 20, "vw": p})
            out[occ] = rows
        return {"bars": out}


class Store(unittest.TestCase):
    DAYS = ["2026-02-23", "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27", "2026-03-02", "2026-03-03"]

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = lambda: datetime(2026, 9, 22, tzinfo=timezone.utc).timestamp()
        self.underlier = lambda symbol, timeframe, start, end: [_daily(d, 100.0) for d in self.DAYS if start[:10] <= d <= end[:10]]

    def store(self, venue):
        store = oh.OptionsHistory(Path(self.dir.name) / "o.sqlite", venue.get, clock=self.clock)
        self.addCleanup(store.close)
        return store

    def test_ingestion_resumes_after_an_interruption_and_records_coverage(self):
        venue = FakeVenue(self.DAYS, fail_once={"260320"})
        store = self.store(venue)
        first = store.ingest(["SPY"], "2026-02-23", "2026-03-03", underlier_bars=self.underlier, band=0.12, max_days=30)
        self.assertEqual(first[0]["failed_chunks"], 1)
        self.assertEqual(first[0]["status"], "partial")
        fetched = [c for c in venue.calls if c[0] == "/v1beta1/options/bars"]
        venue.calls.clear()
        again = store.ingest(["SPY"], "2026-02-23", "2026-03-03", underlier_bars=self.underlier, band=0.12, max_days=30)
        refetched = [c for c in venue.calls if c[0] == "/v1beta1/options/bars"]
        self.assertEqual(len(refetched), 1)  # only the chunk that failed; the listing is not re-read
        self.assertIn("260320", refetched[0][1]["symbols"])
        self.assertEqual(again[0]["status"], "complete")
        self.assertEqual(again[0]["asset"], "option")
        self.assertIn("unavailable", again[0]["quotes"])
        self.assertTrue(fetched)
        venue.calls.clear()
        store.ingest(["SPY"], "2026-02-23", "2026-03-03", underlier_bars=self.underlier, band=0.12, max_days=30)
        self.assertEqual([c for c in venue.calls if c[0] == "/v1beta1/options/bars"], [])  # finished: nothing to fetch
        self.assertEqual(store.covers(["SPY", "QQQ"], "1Day", "2026-02-23T00:00:00Z", "2026-03-03T00:00:00Z"), ["SPY"])

    def test_threads_get_their_own_connection_and_a_finished_threads_is_closed(self):
        import threading
        store = self.store(FakeVenue(self.DAYS))
        store.record_quotes([{"symbol": C1, "bid": 0.40, "ask": 0.42, "as_of": "2026-09-22T14:00:00Z"}], source="opra")
        seen = []
        workers = [threading.Thread(target=lambda: seen.append(len(store.quotes([C1])[C1]))) for _ in range(4)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        self.assertEqual(seen, [1, 1, 1, 1])
        store.db.execute("SELECT 1")  # the main thread's own, still open
        last = threading.Thread(target=store.coverage)
        last.start()
        last.join()
        self.assertEqual(len(store._connections), 2)  # the four finished workers' connections were closed

    def test_a_window_whose_chunks_failed_is_not_coverage_even_with_older_bars_stored(self):
        """Found in review: counting every stored bar of the underlying let a refresh whose every
        chunk failed still read as coverage of its window."""
        store = self.store(FakeVenue(self.DAYS))
        store.ingest(["SPY"], "2026-02-23", "2026-02-27", underlier_bars=self.underlier, band=0.12, max_days=30)
        store.get = FakeVenue(self.DAYS, fail_bars=True).get
        rows = store.ingest(["SPY"], "2026-03-02", "2026-03-03", underlier_bars=self.underlier, band=0.12, max_days=30)
        self.assertEqual((rows[0]["status"], rows[0]["bars"]), ("unavailable", 0))
        self.assertEqual(store.covers(["SPY"], "1Day", "2026-02-23T00:00:00Z", "2026-02-27T00:00:00Z"), ["SPY"])
        self.assertEqual(store.covers(["SPY"], "1Day", "2026-02-23T00:00:00Z", "2026-03-10T00:00:00Z"), [])

    def test_a_refused_listing_is_unavailable_not_zero(self):
        def refuse(path, params):
            raise oh.HistoryError("HTTP 403 Not a path this gateway signs")
        store = oh.OptionsHistory(Path(self.dir.name) / "r.sqlite", refuse, clock=self.clock)
        self.addCleanup(store.close)
        rows = store.ingest(["SPY"], "2026-02-23", "2026-03-03", underlier_bars=self.underlier)
        self.assertEqual((rows[0]["status"], rows[0]["bars"]), ("unavailable", 0))
        self.assertIn("refused", rows[0]["reason"])

    def test_features_recover_the_volatility_and_are_not_seen_before_they_exist(self):
        store = self.store(FakeVenue(self.DAYS))
        store.ingest(["SPY"], "2026-02-23", "2026-03-03", underlier_bars=self.underlier, band=0.12, max_days=30)
        made = store.compute_features("SPY", oh.daily_closes(self.underlier("SPY", "1Day", "2026-02-01", "2026-03-04")))
        self.assertGreater(made, 0)
        row = store.features_at(["SPY"], datetime(2026, 3, 3, 12, tzinfo=timezone.utc).timestamp())["SPY"]
        self.assertEqual(row["day"], "2026-03-02")  # Tuesday noon sees Monday's session, not Tuesday's
        self.assertAlmostEqual(row["atm_iv"], 0.25, places=3)
        self.assertAlmostEqual(row["skew_25d"] or 0.0, 0.0, places=3)  # one volatility for every strike
        self.assertEqual(row["option_trades"], 20 * row["contracts_printed"])
        self.assertIn("trade direction", row["not_available"])
        self.assertIsNone(store.features_at(["SPY"], datetime(2026, 2, 23, 20, tzinfo=timezone.utc).timestamp()).get("SPY"))

    def test_an_equity_replay_sees_a_feature_only_from_when_it_became_available(self):
        code = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "style": "t", "symbols": ["SPY"], "bars": {"timeframe": "1Hour", "limit": 5}, "options_features": True}
PARAMS = {}
def decide(ctx):
    seen = (ctx.get("options_features") or {}).get("SPY") or {}
    days = list((ctx.get("memory") or {}).get("days") or [])
    days.append([ctx["now"], seen.get("day")])
    return {"intents": [], "memory": {"days": days[-20:]}}
'''
        feature = lambda day: {"t": oh.close_stamp(f"{day}T05:00:00Z", "1Day"), "day": day, "atm_iv": 0.2}  # noqa: E731
        steps = [{"t": t, "bars": {"SPY": {"o": 1, "h": 1, "l": 1, "c": 1, "v": 1}}} for t in
                 ("2026-03-02T20:00:00Z", "2026-03-02T21:00:00Z", "2026-03-03T15:00:00Z")]
        tape_ = {"venue": "alpaca", "horizon": "day", "steps": steps, "options_features": {"SPY": [feature("2026-02-27"), feature("2026-03-02")]}}
        result = run_replay(code, {}, tape_, stake=100.0, audit=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["final_memory"]["days"], [["2026-03-02T20:00:00Z", "2026-02-27"], ["2026-03-02T21:00:00Z", "2026-02-27"],
                                                          ["2026-03-03T15:00:00Z", "2026-03-02"]])

    def test_a_refused_prints_endpoint_is_recorded_and_the_bars_still_land(self):
        store = self.store(FakeVenue(self.DAYS))
        rows = store.ingest(["SPY"], "2026-02-23", "2026-03-03", underlier_bars=self.underlier, band=0.12, max_days=30, trades=True)
        self.assertEqual(rows[0]["status"], "complete")
        failed = store.db.execute("SELECT key, state, detail FROM chunks WHERE key LIKE 'trades:%'").fetchall()
        self.assertTrue(failed and all(state == "failed" and "403" in detail for _, state, detail in failed))
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 0)  # unavailable, not zero prints

    def test_the_full_path_from_ingestion_to_a_replay_of_the_tape(self):
        """Store -> tape -> replay: the chain a step shows has printed, is priced from the store,
        and a buy fills only on a later bar."""
        store = self.store(FakeVenue(self.DAYS))
        store.ingest(["SPY"], "2026-02-23", "2026-03-03", underlier_bars=self.underlier, timeframes=("15Min",), band=0.12, max_days=30)

        def underlier(symbol, timeframe, start, end):
            if timeframe == "1Day":
                return self.underlier(symbol, timeframe, start, end)
            return [{"t": f"{d}T{m}:00Z", "o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0, "v": 1e5} for d in self.DAYS
                    for m in ("15:15", "15:30") if start[:10] <= d <= end[:10]]

        needs = {"symbols": ["SPY"], "bars": {"timeframe": "1Day", "limit": 5}, "max_days_to_expiry": 28}
        built = store.tape(needs, "2026-02-23T00:00:00Z", "2026-03-04T00:00:00Z", horizon="day", underlier_bars=underlier,
                           execution="15Min", max_order_usd=500.0)
        self.assertEqual(len(built["steps"]), 2 * len(self.DAYS))
        self.assertTrue(all(isinstance(bar, list) and len(bar) == 6 for step in built["steps"] for bar in step["options"].values()))
        code = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "style": "t", "asset_class": "option", "symbols": ["SPY"], "bars": {"timeframe": "1Day", "limit": 5}}
PARAMS = {}
def decide(ctx):
    chain = sorted(ctx.get("chain") or [], key=lambda r: r["occ"])
    if ctx["now"] != "2026-02-24T15:15:00Z" or not chain:
        return {"intents": []}
    row = chain[0]
    return {"intents": [{"occ": row["occ"], "side": "buy", "quantity": 1, "type": "limit", "limit_price": row["ask"], "reason": "test"}]}
'''
        result = run_replay(code, {}, json.loads(json.dumps(built)), stake=1000.0,
                            limits={"max_position_usd": 600.0, "max_order_usd": 500.0}, audit=True)
        self.assertTrue(result["ok"], result)
        buys = [f for f in result["fill_log"] if f["side"] == "buy"]
        self.assertEqual(len(buys), 1)
        self.assertGreater(buys[0]["t"], "2026-02-24T15:15:00Z")  # not in the bar the decision saw
        self.assertTrue(all(c["first_print"] >= "2026-02-23T15:15:00Z" for c in built["contracts"].values()))

    def test_the_tape_lists_a_contract_only_from_its_first_print(self):
        store = self.store(FakeVenue(self.DAYS))
        store.ingest(["SPY"], "2026-02-23", "2026-03-03", underlier_bars=self.underlier, timeframes=("1Day",), band=0.12, max_days=30)
        needs = {"symbols": ["SPY"], "bars": {"timeframe": "1Day", "limit": 5}, "max_days_to_expiry": 28}
        built = store.tape(needs, "2026-02-23T00:00:00Z", "2026-03-04T00:00:00Z", horizon="day", underlier_bars=self.underlier,
                           execution="1Day", max_order_usd=75.0)
        self.assertEqual(built["asset_class"], "option")
        self.assertTrue(built["contracts"])
        self.assertTrue(all(c["first_print"] >= "2026-02-24" for c in built["contracts"].values()))
        self.assertTrue(all(json.dumps(built)))  # plain JSON for the box


if __name__ == "__main__":
    unittest.main()


from league import seeds  # noqa: E402
from league.tests.test_house import HouseCase  # noqa: E402
from league.ledger import now_iso  # noqa: E402


BUYER_WITH_FEATURES = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "t", "symbols": ["BTC/USD"], "bars": {"timeframe": "5Min", "limit": 5}, "options_features": True}
PARAMS = {}
def decide(ctx):
    return {"intents": [], "memory": {"seen": sorted((ctx.get("options_features") or {}))}}
'''


class CoveredStore:
    """An options history that covers everything asked of it, and records the tapes asked for."""

    def __init__(self, covered=True):
        self.covered, self.tapes = covered, []

    def covers(self, symbols, timeframe, start, end):
        return [s.upper() for s in symbols] if self.covered else []

    def tape(self, needs, start, end, **kw):
        self.tapes.append((dict(needs), kw["execution"], kw["max_order_usd"]))
        self.windows = getattr(self, "windows", []) + [(start, end)]
        return {"venue": "alpaca", "asset_class": "option", "horizon": kw["horizon"], "steps": [{"t": start}], "contracts": {}}

    def features_at(self, symbols, now_ts):
        return {s: {"t": "2026-09-10T04:00:00Z", "atm_iv": 0.2} for s in symbols}

    def feature_series(self, symbols):
        return {s: [{"t": "2026-09-10T04:00:00Z", "atm_iv": 0.2}] for s in symbols}


class InTheHouse(HouseCase):
    def test_without_history_the_options_desk_keeps_paper_as_its_replay(self):
        self.house.options_history = CoveredStore(covered=False)
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)

    def test_with_history_a_newcomer_is_replayed_first_on_an_options_tape(self):
        store = self.house.options_history = CoveredStore()
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        self.assertEqual(self.house.evaluator.rung(agent.id), 0)  # admission by replay, not a free paper seat
        key, built = self.house.tape_for(agent.needs)
        self.assertTrue(key.startswith("options:"))
        self.assertEqual(built["asset_class"], "option")
        self.assertEqual(store.tapes[0][1:], ("15Min", 75.0))

    def test_the_live_chain_keeps_its_opra_quotes_for_the_replay(self):
        with tempfile.TemporaryDirectory() as root:
            store = self.house.options_history = oh.OptionsHistory(Path(root) / "q.sqlite")
            self.addCleanup(store.close)
            broker = self.house.books["alpaca-paper"].broker
            broker.option_feed = "opra"
            broker.option_chain = lambda symbol, *, expiry_from, expiry_to: [
                {"symbol": "F261009C00013000", "underlying": "F", "expiry": "2026-10-09", "strike": 13.0, "right": "call",
                 "bid": 0.40, "ask": 0.44, "as_of": "2026-09-22T14:00:00Z", "iv": 0.3, "delta": 0.5, "volume": 1.0}]
            rows = self.house._chain(["F"], 21, 0.75, {"F": {"bid": 12.9, "ask": 13.0}})
            self.assertEqual(len(rows), 1)
            self.assertEqual(store.quotes(["F261009C00013000"])["F261009C00013000"][0]["ask"], 0.44)

    def test_the_history_is_refreshed_once_a_day_after_the_close(self):
        self.house.options_history = CoveredStore()
        calls = []
        self.house._refresh_options_history = lambda: calls.append(self.clock())
        self.clock.now = datetime(2026, 9, 21, 19, 0, tzinfo=timezone.utc).timestamp()  # 15:00 New York: not yet
        self.house.tick()
        self.house.wait(5)
        self.assertEqual(calls, [])
        self.clock.now = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc).timestamp()  # 18:00 New York
        self.house.tick()
        self.house.wait(5)
        self.house.tick()
        self.house.wait(5)
        self.assertEqual(len(calls), 1)

    def test_a_strategy_reading_features_the_house_has_no_history_of_is_not_replayed(self):
        store = self.house.options_history = CoveredStore()
        code = BUYER_WITH_FEATURES
        needs = {"venue": "alpaca", "horizon": "hour", "style": "t", "symbols": ["BTC/USD"], "bars": {"timeframe": "5Min", "limit": 5}, "options_features": True}
        agent = self.seated(code=code)
        store.feature_series = lambda symbols: {}
        with self.assertRaises(ValueError) as caught:
            self.house._run_replay(agent, code, needs, {})
        self.assertIn("unsupported input: no options-feature history for BTC/USD", str(caught.exception))
        self.assertEqual(list(self.house.ledger.iter(kinds="eval.trial")), [])  # unavailable data is not a trial

    def test_a_live_wake_is_handed_the_same_stored_feature_rows(self):
        self.house.options_history = CoveredStore()
        agent = self.seated(code=BUYER_WITH_FEATURES)
        ctx = self.house.snapshot(agent, self.house.book_of(agent))
        self.assertEqual(ctx["options_features"], {"BTC/USD": {"t": "2026-09-10T04:00:00Z", "atm_iv": 0.2}})
        plain = self.seated(name="plain")
        self.assertNotIn("options_features", self.house.snapshot(plain, self.house.book_of(plain)))

    def test_the_daily_job_backfills_what_living_options_agents_trade_then_keeps_it_current(self):
        from unittest import mock
        store = self.house.options_history = CoveredStore(covered=False)
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        calls = []

        def refresh(store_, symbols, underlier, **kw):
            calls.append((sorted(symbols), kw["days"], tuple(kw["timeframes"])))
            return {"features": {}, "coverage": []}

        with mock.patch("league.options_history.refresh", refresh):
            self.house._refresh_options_history()
            store.covered = True
            self.house._refresh_options_history()
        span = self.house.settings.replay_days * 6 + 5
        self.assertEqual(calls[0], (sorted(agent.needs["symbols"]), span, ("1Day", "15Min")))  # backfill the whole window once
        self.assertEqual(calls[1], (["IWM", "QQQ", "SPY"], span, ("1Day",)))
        self.assertEqual([c[1] for c in calls[2:]], [10, 10])  # then the last ten days

    def test_the_sealed_box_runs_an_options_tape_from_the_kit_alone(self):
        """In the box there is no `league` package: replay.py reaches options_replay.py and
        options_history.py beside it, and needs no sqlite3."""
        steps = [step("2026-03-02T15:00:00Z", {C1: [0.40, 0.42, 0.38, 0.40, 50.0, 10]}),
                 step("2026-03-02T15:15:00Z", {C1: [0.40, 0.41, 0.39, 0.40, 50.0, 10]})]
        run = self.house.sandbox.replay("box-test", STRATEGY, {"occ": C1, "buy_at": "2026-03-02T15:00:00Z", "limit": 0.40}, tape(steps),
                                        stake=1000.0, limits=LIMITS, timeout=120)
        self.assertTrue(run.result["ok"], run.result)
        self.assertEqual((run.result["asset_class"], run.result["fills"], run.result["fees_usd"]), ("option", 1, 0.05))

    def test_a_failed_daily_job_is_tried_again_an_hour_later_and_a_finished_one_not_again_that_day(self):
        self.house.options_history = CoveredStore()
        calls = []

        def job():
            calls.append(self.clock())
            if len(calls) == 1:
                raise RuntimeError("gateway down")
            self.house._state["options_history_day"] = "2026-09-21"

        self.house._refresh_options_history = job
        self.clock.now = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc).timestamp()  # 18:00 New York
        for minutes in (0, 10, 61, 75, 130):
            self.clock.now = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc).timestamp() + minutes * 60
            self.house.tick()
            self.house.wait(5)
        self.assertEqual([round((c - calls[0]) / 60) for c in calls], [0, 61])

    def test_an_options_strategy_never_gets_the_history_stores_equity_tape_nor_the_holdout(self):
        store = self.house.options_history = CoveredStore()
        self.house._deep_tape = lambda needs: ("deep:equity", {"venue": "alpaca", "steps": []})  # a store that covers the underlyings
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        key, built = self.house.tape_for(agent.needs)
        self.assertTrue(key.startswith("options:"))
        self.assertEqual(built["asset_class"], "option")
        now = now_iso(self.clock)
        self.house.holdout_window = ("2026-01-01", now[:10])  # a holdout that ends today
        self.house._tapes.clear()
        self.house.tape_for(agent.needs)
        self.assertGreater(store.windows[-1][0], now[:10])  # the options window starts after it, never inside it
        equity = self.house.tape_for({"venue": "alpaca", "horizon": "day", "symbols": ["SPY"], "bars": {"timeframe": "1Day", "limit": 5}})
        self.assertEqual(equity[0], "deep:equity")  # the equity desks still get the history store

    def test_the_switch_turns_it_off(self):
        self.house.options_history = CoveredStore()
        self.house.settings.options_replay = False
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)


# ---------------------------------------------------------------------------------------------------------
# Structures (Sept 25, 2026, the options-desk run): a structure agent's replay, held as ONE position at
# S = net value + collateral, filled at the CONSERVATIVE touch of every leg at once, never in the bar the
# decision saw, settled at its value at the expiry's close, one trade a structure.

from league import parameters  # noqa: E402
from league import structure_core  # noqa: E402

STRUCTURE_STRATEGY = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "style": "structure-test", "asset_class": "option", "structures": True,
         "symbols": ["SPY"], "bars": {"timeframe": "1Day", "limit": 5}, "max_days_to_expiry": 7,
         "parameter_rules": {"bounds": {"max_debit": [0.05, 0.95], "take_profit": [0.05, 0.95]}}}
PARAMS = {"structure": "debit_vertical", "legs": [], "open_at": "", "close_at": "", "limit": 0.0, "close_limit": 0.0, "quantity": 1,
          "max_debit": 0.0, "take_profit": 0.0, "width": 1, "dte_min": 0, "dte_max": 7, "entry_delta": 0.3, "profit_target": 0.5,
          "stop_loss": 2.0, "exit_minutes_before_close": 30, "max_open": 1, "single": ""}

def decide(ctx):
    p = ctx["params"]
    out = []
    limit = p["limit"] or p["max_debit"]
    if ctx["now"] == p["open_at"]:
        out.append({"structure": p["structure"], "action": "open", "quantity": p["quantity"], "legs": p["legs"], "limit_price": limit, "reason": "test open"})
    if ctx["now"] == p["close_at"]:
        out.append({"structure": p["structure"], "action": "close", "quantity": p["quantity"], "legs": p["legs"],
                    "limit_price": p["close_limit"] or p["take_profit"], "reason": "test close"})
    if p["single"] and ctx["now"] == p["open_at"]:
        out.append({"occ": p["single"], "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.5, "reason": "a single leg"})
    held = [{k: x.get(k) for k in ("structure", "quantity", "average_cost", "mark", "natural_open", "natural_mark", "pnl_usd",
                                  "max_loss_usd", "max_gain_usd", "kind", "expiry")} for x in ctx.get("positions") or [] if x.get("structure")]
    seen = dict(ctx.get("memory") or {})
    seen[ctx["now"]] = {"chain": sorted(r["occ"] for r in ctx.get("chain") or []), "structures": len(ctx.get("structures") or []),
                        "held": held, "orders": [o.get("structure") for o in ctx.get("open_orders") or []]}
    return {"intents": out, "memory": dict(list(seen.items())[-6:])}
'''
EXP = "2026-09-25"  # a Friday; 2026-09-22..25 is EDT (UTC-4): 14:30 New York is 18:30Z, 15:30 is 19:30Z, 16:00 is 20:00Z
SLIMITS = {"max_position_usd": 100.0, "max_order_usd": 75.0}


def socc(strike, right="C", expiry="260925"):
    return f"SPY{expiry}{right}{int(strike * 1000):08d}"


def contract(code, first="2026-09-22T13:45:00Z"):
    parsed = oh.parse_occ(code)
    return {"underlying": "SPY", "expiry": parsed["expiry"], "strike": parsed["strike"], "right": parsed["right"], "first_print": first}


def stape(steps, codes, **extra):
    return {"venue": "alpaca", "asset_class": "option", "horizon": "day", "symbols": ["SPY"], "steps": steps,
            "contracts": {c: contract(c) for c in codes},
            "chain_rules": {"max_days_to_expiry": 7, "moneyness": 0.2, "per_underlying": 80, "afford_per_share": None, "structures": True},
            "spread_model": dict(oh.SPREAD_MODEL), "liquidity": dict(oh.LIQUIDITY), "fee_per_contract_usd": 0.05, "multiplier": 100,
            "warmup_bars": {}, "half_spread_bps": 1.0, "step_seconds": 900, **extra}


def sstep(t, prices, spot=585.40, v=50.0, n=10, volumes=None):
    options = {code: [price, price, price, price, (volumes or {}).get(code, v), n] for code, price in prices.items()}
    return {"t": t, "bars": {}, "execution_bars": {"SPY": bar(spot, spot, spot, spot, 1000)}, "options": options}


def srun(steps, codes, stake=1000.0, limits=None, strategy=STRUCTURE_STRATEGY, **params):
    result = run_replay(strategy, params, stape(steps, codes), stake=stake, limits=limits or SLIMITS, audit=True)
    assert result["ok"], result
    return result


VERTICAL = [socc(585), socc(586)]
VLEGS = [{"occ": socc(585), "role": "long"}, {"occ": socc(586), "role": "short"}]
CONDOR = [socc(580, "P"), socc(581, "P"), socc(590), socc(591)]
CLEGS = [{"occ": socc(580, "P"), "role": "long"}, {"occ": socc(581, "P"), "role": "short"},
         {"occ": socc(590), "role": "short"}, {"occ": socc(591), "role": "long"}]
VPRICES = {socc(585): 1.20, socc(586): 0.70}
CPRICES = {socc(580, "P"): 0.10, socc(581, "P"): 0.40, socc(590): 0.35, socc(591): 0.08}


class Structures(unittest.TestCase):
    def test_a_debit_vertical_by_hand(self):
        steps = [sstep("2026-09-22T13:45:00Z", VPRICES), sstep("2026-09-22T14:00:00Z", VPRICES), sstep("2026-09-22T14:15:00Z", VPRICES),
                 sstep("2026-09-22T14:30:00Z", {socc(585): 1.60, socc(586): 0.85})]
        r = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-22T13:45:00Z", limit=0.60, close_at="2026-09-22T14:15:00Z", close_limit=0.50)
        fills = [f for f in r["fill_log"] if f["side"] in ("buy", "sell")]
        # opened in the NEXT bar at the conservative ask: long 1.20 + 4% = 1.248, short 0.70 - 4% = 0.672 -> 0.576
        self.assertEqual([(f["t"], f["side"], f["price"], f["fee"]) for f in fills],
                         [("2026-09-22T14:00:00Z", "buy", 0.576, 0.1), ("2026-09-22T14:30:00Z", "sell", 0.652, 0.1)])
        # closed at the conservative bid: long 1.60 - 4% = 1.536, short 0.85 + 4% = 0.884 -> 0.652; ONE trade
        self.assertEqual(r["trades"], 1)
        self.assertAlmostEqual(r["final_equity"], 1000.0 + (0.652 - 0.576) * 100 - 0.2, places=6)
        self.assertAlmostEqual(r["trade_returns"][0], ((0.652 - 0.576) * 100 - 0.2) / 1000.0, places=9)
        self.assertEqual(r["options"]["structures"]["opened"], 1)
        self.assertEqual(r["options"]["structures"]["closed"], 1)
        # marked at the SHOWN bid: long 1.20 - 4.5% = 1.146, short 0.70 + 4.5% = 0.7315 -> 0.4145; fees in the average cost
        held = r["final_memory"]["2026-09-22T14:00:00Z"]["held"][0]
        self.assertEqual((held["structure"], held["kind"], held["expiry"], held["quantity"]), ("debit_vertical", "debit", EXP, 1.0))
        self.assertAlmostEqual(held["mark"], 0.4145, places=9)
        self.assertAlmostEqual(held["average_cost"], 0.577, places=9)
        self.assertAlmostEqual(held["natural_open"], 0.577, places=6)
        self.assertAlmostEqual(held["pnl_usd"], -16.25, places=6)
        self.assertAlmostEqual(held["max_loss_usd"], 57.7, places=6)
        self.assertAlmostEqual(held["max_gain_usd"], 42.3, places=6)
        self.assertEqual(r["digest"]["all"]["trades"], 1)

    def test_nothing_fills_in_the_decisions_bar_nor_when_a_leg_did_not_print(self):
        only = [sstep("2026-09-22T13:45:00Z", VPRICES)]
        self.assertEqual(srun(only, VERTICAL, legs=VLEGS, open_at="2026-09-22T13:45:00Z", limit=0.70)["fills"], 0)
        steps = [sstep("2026-09-22T13:45:00Z", VPRICES), sstep("2026-09-22T14:00:00Z", {socc(585): 1.20}),
                 sstep("2026-09-22T14:15:00Z", VPRICES)]
        r = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-22T13:45:00Z", limit=0.70)
        self.assertEqual([f["t"] for f in r["fill_log"]], ["2026-09-22T14:15:00Z"])  # the bar where BOTH legs printed

    def test_a_limit_under_the_conservative_ask_does_not_fill(self):
        steps = [sstep("2026-09-22T13:45:00Z", VPRICES), sstep("2026-09-22T14:00:00Z", VPRICES)]
        r = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-22T13:45:00Z", limit=0.57)  # the conservative ask is 0.576
        self.assertEqual(r["fills"], 0)
        self.assertEqual(r["expired_orders"], 0)  # still resting: a day order ends at 16:00

    def test_an_iron_condor_by_hand_settled_at_intrinsic(self):
        steps = [sstep("2026-09-25T13:45:00Z", CPRICES), sstep("2026-09-25T14:00:00Z", CPRICES),
                 sstep("2026-09-25T19:30:00Z", CPRICES), sstep("2026-09-25T19:45:00Z", {k: v * 1.5 for k, v in CPRICES.items()}),
                 sstep("2026-09-25T20:00:00Z", {}, spot=585.60)]
        r = srun(steps, CONDOR, structure="iron_condor", legs=CLEGS, open_at="2026-09-25T13:45:00Z", limit=0.30)
        opened = [f for f in r["fill_log"] if f["side"] == "buy"]
        # conservative ask: K 1 + long asks (0.10 + 0.01, 0.08 + 0.01) - short bids (0.40 - 0.016, 0.35 - 0.014) = 0.48:
        # a 0.52 credit, within the 0.30 least credit (a held limit of 0.70); fee 4 contracts x $0.05
        self.assertEqual([(f["t"], f["price"], f["fee"]) for f in opened], [("2026-09-25T14:00:00Z", 0.48, 0.2)])
        held = r["final_memory"]["2026-09-25T14:00:00Z"]["held"][0]
        # marked at the shown bid: 1 + 0.09 + 0.07 - 0.418 - 0.3658 (each leg's shown quote, to four places); its
        # natural mark is what buying it back would cost
        shown = {code: oh.display_quote(price) for code, price in CPRICES.items()}
        mark = 1 + shown[socc(580, "P")][0] + shown[socc(591)][0] - shown[socc(581, "P")][1] - shown[socc(590)][1]
        self.assertAlmostEqual(held["mark"], mark, places=9)
        self.assertAlmostEqual(mark, 0.37625, places=3)
        self.assertAlmostEqual(held["natural_mark"], 1 - mark, places=6)
        self.assertEqual(held["kind"], "credit")
        self.assertAlmostEqual(held["natural_open"], 1 - 0.482, places=6)  # the credit received, net of the fee a share
        # the House offered it from 15:30 at its conservative bid (the 15:45 bar was dearer: no fill) and it
        # was SETTLED at the close at intrinsic: SPY 585.60 is between the shorts, so S = K = 1.00
        self.assertGreaterEqual(r["options"]["structures"]["house_close_offers"], 1)
        settled = [f for f in r["fill_log"] if f["side"] == "settle"]
        self.assertEqual([(f["t"], f["price"], f["fee"]) for f in settled], [("2026-09-25T20:00:00Z", 1.0, 0.0)])
        self.assertEqual(r["trades"], 1)
        self.assertEqual(r["options"]["structures"]["settled_at_expiry"], 1)
        self.assertAlmostEqual(r["final_equity"], 1000.0 + (1.0 - 0.48) * 100 - 0.2, places=6)
        self.assertEqual(r["open_positions"], 0)

    def test_the_house_close_fills_at_the_conservative_bid_and_a_loser_settles_at_its_intrinsic(self):
        steps = [sstep("2026-09-25T13:45:00Z", VPRICES), sstep("2026-09-25T14:00:00Z", VPRICES),
                 sstep("2026-09-25T19:30:00Z", VPRICES), sstep("2026-09-25T19:45:00Z", VPRICES)]
        r = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-25T13:45:00Z", limit=0.60)
        sold = [f for f in r["fill_log"] if f["side"] == "sell"]
        # offered at 15:30 at the conservative bid then (1.20 - 0.048 - (0.70 + 0.028) = 0.424), filled at 15:45 at it
        self.assertEqual([(f["t"], f["price"]) for f in sold], [("2026-09-25T19:45:00Z", 0.424)])
        self.assertEqual(r["trade_log"][0]["how"] if "trade_log" in r else "expiry rule", "expiry rule")
        # a vertical still held at the close, SPY under both strikes: settled at S = 0, a loss of its debit, never more
        steps = [sstep("2026-09-25T13:45:00Z", VPRICES), sstep("2026-09-25T14:00:00Z", VPRICES), sstep("2026-09-25T20:00:00Z", {}, spot=584.0)]
        r = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-25T13:45:00Z", limit=0.60)
        self.assertEqual([(f["side"], f["price"]) for f in r["fill_log"]], [("buy", 0.576), ("settle", 0.0)])
        self.assertAlmostEqual(r["final_equity"], 1000.0 - 57.6 - 0.1, places=6)
        self.assertEqual(r["digest"]["worst"][0]["how"], "settled at intrinsic on the underlying's close")

    def test_no_structure_is_opened_on_its_expiry_day_from_1430_new_york(self):
        steps = [sstep("2026-09-25T18:15:00Z", VPRICES), sstep("2026-09-25T18:30:00Z", VPRICES), sstep("2026-09-25T18:45:00Z", VPRICES)]
        r = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-25T18:30:00Z", limit=0.70)
        self.assertEqual(r["fills"], 0)
        self.assertIn("no structure is opened on its earliest expiry day from 14:30 New York", " ".join(r["refusal_reasons"]))
        before = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-25T18:15:00Z", limit=0.70)
        self.assertEqual(before["fills"], 1)  # 14:15 New York: still open for entries

    def test_participation_counts_a_butterflys_body_twice(self):
        fly = [socc(584), socc(585), socc(586)]
        legs = [{"occ": socc(584), "role": "long"}, {"occ": socc(585), "role": "short", "ratio": 2}, {"occ": socc(586), "role": "long"}]
        prices = {socc(584): 1.80, socc(585): 1.20, socc(586): 0.75}
        thin = {socc(585): 15.0}  # 10% of 15 is 1.5 contracts: one butterfly needs 2 of the body
        steps = [sstep("2026-09-22T13:45:00Z", prices), sstep("2026-09-22T14:00:00Z", prices, volumes=thin),
                 sstep("2026-09-22T14:15:00Z", prices, volumes={socc(585): 20.0})]
        r = srun(steps, fly, structure="long_butterfly", legs=legs, open_at="2026-09-22T13:45:00Z", limit=0.40)
        self.assertEqual([f["t"] for f in r["fill_log"]], ["2026-09-22T14:15:00Z"])
        self.assertEqual(r["options"]["liquidity_misses"], 1)
        # conservative ask: 1.80 + 0.072 + 0.75 + 0.03 - 2 x (1.20 - 0.048) = 0.348; the fee is 4 contracts
        self.assertEqual((r["fill_log"][0]["price"], r["fill_log"][0]["fee"]), (0.348, 0.2))

    def test_a_calendar_settles_at_its_far_legs_bid_less_its_near_legs_intrinsic_or_is_not_evaluated(self):
        near, far = socc(585, expiry="260925"), socc(585, expiry="261002")
        legs = [{"occ": near, "role": "short"}, {"occ": far, "role": "long"}]
        prices = {near: 1.00, far: 3.00}
        steps = [sstep("2026-09-25T13:45:00Z", prices), sstep("2026-09-25T14:00:00Z", prices), sstep("2026-09-25T20:00:00Z", {}, spot=586.0)]
        wide = {"max_position_usd": 300.0, "max_order_usd": 250.0}
        r = srun(steps, [near, far], structure="calendar", legs=legs, open_at="2026-09-25T13:45:00Z", limit=2.20, limits=wide)
        # opened at 3.00 + 0.12 - (1.00 - 0.04) = 2.16; settled at the far leg's last conservative bid 2.88 less 1.00 intrinsic
        self.assertEqual([(f["side"], f["price"]) for f in r["fill_log"]], [("buy", 2.16), ("settle", 1.88)])
        self.assertEqual(r["trade_log"][0]["how"] if "trade_log" in r else r["digest"]["worst"][0]["how"],
                         "settled: the far leg's bid less the near leg's intrinsic")
        # no price of the underlying on its expiry day (the tape jumps to Monday): refunded at cost, not a trade, not a loss
        gap = [sstep("2026-09-24T13:45:00Z", prices), sstep("2026-09-24T14:00:00Z", prices),
               {"t": "2026-09-28T13:45:00Z", "bars": {}, "execution_bars": {}, "options": {socc(590): [0.5, 0.5, 0.5, 0.5, 50.0, 10]}}]
        r = srun(gap, [near, far, socc(590)], structure="calendar", legs=legs, open_at="2026-09-24T13:45:00Z", limit=2.20, limits=wide)
        self.assertEqual(r["options"]["structures"]["not_evaluated"], 1)
        self.assertEqual(r["trades"], 0)
        self.assertAlmostEqual(r["final_equity"], 1000.0 - 0.1, places=6)  # the fee stays paid
        # a far leg the history never saw at all: the calendar is not evaluated (refused), never a loss
        later = [{"occ": near, "role": "short"}, {"occ": socc(585, expiry="261023"), "role": "long"}]
        r = srun(steps, [near, far], structure="calendar", legs=later, open_at="2026-09-25T13:45:00Z", limit=2.20, limits=wide)
        self.assertEqual((r["fills"], r["trades"], r["options"]["structures"]["unseen_leg_refusals"]), (0, 0, 1))
        self.assertIn("not evaluated: the history holds no prints of a leg", " ".join(r["refusal_reasons"]))

    def test_the_context_is_the_houses_structure_context(self):
        cheap, dear, today_call = socc(585), socc(575), socc(586)
        codes = [cheap, dear, today_call, socc(584), socc(586, "C", "260922")]
        prices = {cheap: 1.20, dear: 10.50, today_call: 0.70, socc(584): 1.80, socc(586, "C", "260922"): 0.30}
        steps = [sstep("2026-09-22T13:45:00Z", prices), sstep("2026-09-22T18:15:00Z", prices), sstep("2026-09-22T18:30:00Z", prices)]
        r = srun(steps, codes, open_at="never")
        seen = r["final_memory"]
        morning, cut = seen["2026-09-22T18:15:00Z"]["chain"], seen["2026-09-22T18:30:00Z"]["chain"]
        self.assertIn(dear, morning)  # $10.50 a share: over a single contract's $0.75 line, shown to a structure agent
        self.assertIn(socc(586, "C", "260922"), morning)  # expiring today, before 14:30 New York
        self.assertNotIn(socc(586, "C", "260922"), cut)  # and not from 14:30
        self.assertGreater(seen["2026-09-22T18:15:00Z"]["structures"], 0)  # ctx["structures"]: structure_core.candidates
        self.assertGreater(r["options"]["structures"]["candidates_shown"], 0)

    def test_the_features_and_feeds_it_declares_as_a_live_wake_sees_them(self):
        strategy = STRUCTURE_STRATEGY.replace('"max_days_to_expiry": 7,', '"max_days_to_expiry": 7, "options_features": True, "feeds": {"earnings": ["SPY"]},')
        strategy = strategy.replace('"held": held,', '"held": held, "iv": (ctx.get("options_features") or {}).get("SPY", {}).get("atm_iv"), '
                                    '"feed": sorted(((ctx.get("feeds") or {}).get("earnings") or {}).get("SPY", {}).items()),')
        steps = [sstep("2026-09-22T13:45:00Z", VPRICES), sstep("2026-09-23T13:45:00Z", VPRICES)]
        tape = stape(steps, VERTICAL, options_features={"SPY": [{"t": "2026-09-22T04:00:00Z", "atm_iv": 0.11}, {"t": "2026-09-23T04:00:00Z", "atm_iv": 0.13}]},
                     feeds={"earnings": {"SPY": [{"t": "2026-09-23T12:00:00Z", "filed": "8-K"}]}})
        r = run_replay(strategy, {"open_at": "never"}, tape, stake=1000.0, limits=SLIMITS, audit=True)
        self.assertTrue(r["ok"], r)
        seen = r["final_memory"]
        self.assertEqual((seen["2026-09-22T13:45:00Z"]["iv"], seen["2026-09-23T13:45:00Z"]["iv"]), (0.11, 0.13))  # never a row before it existed
        self.assertEqual((seen["2026-09-22T13:45:00Z"]["feed"], seen["2026-09-23T13:45:00Z"]["feed"]),
                         ([], [["filed", "8-K"], ["t", "2026-09-23T12:00:00Z"]]))

    def test_the_chain_shows_at_most_eighty_an_underlying_nearest_the_money(self):
        codes = [socc(k, right) for k in range(560, 611) for right in ("C", "P")]  # 102 contracts
        prices = {c: 1.0 for c in codes}
        r = srun([sstep("2026-09-22T13:45:00Z", prices), sstep("2026-09-22T14:00:00Z", prices)], codes, open_at="never")
        chain = r["final_memory"]["2026-09-22T14:00:00Z"]["chain"]
        self.assertEqual(len(chain), 80)
        self.assertTrue(all(abs(int(c[-8:]) / 1000 - 585.40) <= 20.5 for c in chain))

    def test_who_may_send_what(self):
        steps = [sstep("2026-09-22T13:45:00Z", VPRICES), sstep("2026-09-22T14:00:00Z", VPRICES)]
        r = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-22T13:45:00Z", limit=0.60, single=socc(585))
        self.assertIn("a structure agent's book holds structures only", " ".join(r["refusal_reasons"]))
        self.assertEqual(r["fills"], 1)  # the structure still went through
        plain = STRUCTURE_STRATEGY.replace('"structures": True,', "")
        self.assertNotIn('"structures": True', plain)
        r = srun(steps, VERTICAL, strategy=plain, legs=VLEGS, open_at="2026-09-22T13:45:00Z", limit=0.60)
        self.assertEqual(r["fills"], 0)
        self.assertIn("a structure intent is for a structure agent", " ".join(r["refusal_reasons"]))
        r = srun(steps, VERTICAL, legs=[{"occ": socc(586), "role": "long"}, {"occ": socc(585), "role": "short"}],
                 open_at="2026-09-22T13:45:00Z", limit=0.60)
        self.assertIn("not a structure order: not a debit_vertical", " ".join(r["refusal_reasons"]))
        r = srun(steps, VERTICAL, legs=VLEGS, open_at="2026-09-22T13:45:00Z", limit=0.60, quantity=2)
        self.assertIn("over the order cap", " ".join(r["refusal_reasons"]))  # 2 x 0.60 x 100 = $120 of maximum loss

    def test_a_structure_strategys_params_are_ordinary_params_an_edit_replays(self):
        """X1 `edit_params` (`House._edit_replay`) and the lab replay a PARAMS change of the same code: the
        spec's structure PARAMS are plain numbers the House can bound, mutate and replay, when the
        strategy declares their bounds (`NEEDS.parameter_rules`); `max_open` is a standard count."""
        ns = {}
        exec(STRUCTURE_STRATEGY, ns)  # noqa: S102 - the test's own strategy
        needs, params = ns["NEEDS"], dict(ns["PARAMS"], legs=VLEGS, open_at="2026-09-22T13:45:00Z", max_debit=0.55, take_profit=0.5)
        parameters.require_valid(params, needs)
        mutable = parameters.inspect(params, needs)["mutable"]
        self.assertTrue({"max_debit", "take_profit", "max_open"} <= set(mutable), mutable)
        child = parameters.mutate(params, seed="structure-edit", needs=needs)
        self.assertEqual(len([k for k in params if params[k] != child[k]]), 1)
        steps = [sstep("2026-09-22T13:45:00Z", VPRICES), sstep("2026-09-22T14:00:00Z", VPRICES)]
        tight = srun(steps, VERTICAL, **params)  # a debit of at most 0.55 does not meet the 0.576 conservative ask
        edited = srun(steps, VERTICAL, **dict(params, max_debit=0.60))  # the edit: the same code, one PARAM
        self.assertEqual((tight["fills"], edited["fills"]), (0, 1))
        self.assertEqual(edited["params"]["max_debit"], 0.60)
        self.assertEqual(tight["code_sha256"], edited["code_sha256"])

    def test_a_replay_is_the_same_in_every_process(self):
        codes = [socc(k, right) for k in range(575, 596) for right in ("C", "P")]
        prices = {c: round(0.2 + abs(585 - int(c[-8:]) / 1000) * 0.1, 2) for c in codes}
        steps = [sstep("2026-09-22T13:45:00Z", prices), sstep("2026-09-22T14:00:00Z", prices)]
        tape = json.dumps(stape(steps, codes))
        code = "import json\nfrom league.replay import run_replay\n" \
               f"r = run_replay({STRUCTURE_STRATEGY!r}, {{'open_at': 'never'}}, json.loads({tape!r}), stake=1000.0, limits={SLIMITS!r}, audit=True)\n" \
               "print(json.dumps(r['final_memory'], sort_keys=True))"
        import os
        import subprocess
        import sys
        runs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                               env={**os.environ, "PYTHONHASHSEED": seed}, cwd=str(Path(__file__).resolve().parents[2])).stdout
                for seed in ("1", "2", "3")}
        self.assertEqual(len(runs), 1)  # a tie (a call and a put of one strike) is broken by the code, not by hashing


class StructureTape(unittest.TestCase):
    def test_a_structure_tape_has_no_affordability_line_and_keeps_the_chains_band(self):
        with tempfile.TemporaryDirectory() as root:
            store = oh.OptionsHistory(Path(root) / "h.sqlite")
            codes = {socc(585): 1.2, socc(575): 10.5, socc(460): 0.05, socc(585, "C", "261016"): 6.0}
            for code in codes:
                parsed = oh.parse_occ(code)
                store.db.execute("INSERT INTO contracts VALUES (?, 'SPY', ?, ?, ?, 100, 'active', '')", (code, parsed["expiry"], parsed["strike"], parsed["right"]))
            for t in ("2026-09-22T14:00:00Z", "2026-09-22T14:15:00Z"):
                for code, price in codes.items():
                    store.db.execute("INSERT INTO bars VALUES (?, '15Min', ?, ?, ?, ?, ?, 50, 10, ?)", (code, t, price, price, price, price, price))
            store.db.commit()

            def underlier(symbol, timeframe, start, end):
                return [{"t": t, "o": 585.4, "h": 585.4, "l": 585.4, "c": 585.4, "v": 1000.0}
                        for t in ("2026-09-22T14:00:00Z", "2026-09-22T14:15:00Z") if start <= t <= end]
            needs = {"symbols": ["SPY"], "bars": {"timeframe": "15Min", "limit": 5}, "structures": True}
            built = store.tape(needs, "2026-09-22T00:00:00Z", "2026-09-22T23:59:59Z", horizon="day", underlier_bars=underlier,
                               execution="15Min", max_order_usd=75.0)
            self.assertEqual(set(built["contracts"]), {socc(585), socc(575)})  # $10.50 kept; 460 is 21% away; Oct 16 past 7 days
            self.assertEqual(built["chain_rules"]["per_underlying"], 80)
            self.assertIsNone(built["chain_rules"]["afford_per_share"])
            single = store.tape({**needs, "structures": False}, "2026-09-22T00:00:00Z", "2026-09-22T23:59:59Z", horizon="day",
                                underlier_bars=underlier, execution="15Min", max_order_usd=75.0)
            self.assertNotIn(socc(575), single["contracts"])  # a single-contract tape keeps its affordability line
            local = oh.stored_underlier  # the local copy's reader refuses a store with no underlier bars
            with self.assertRaises(oh.HistoryError):
                local(store)

    def test_a_structure_tape_over_its_budget_drops_its_oldest_steps(self):
        with tempfile.TemporaryDirectory() as root:
            store = oh.OptionsHistory(Path(root) / "h.sqlite")
            store.db.execute("INSERT INTO contracts VALUES (?, 'SPY', '2026-09-25', 585.0, 'call', 100, 'active', '')", (socc(585),))
            stamps = ["2026-09-22T14:00:00Z", "2026-09-22T14:15:00Z", "2026-09-22T14:30:00Z"]
            for t in stamps:
                store.db.execute("INSERT INTO bars VALUES (?, '15Min', ?, 1.2, 1.2, 1.2, 1.2, 50, 10, 1.2)", (socc(585), t))
            store.db.commit()

            def underlier(symbol, timeframe, start, end):
                return [{"t": t, "o": 585.4, "h": 585.4, "l": 585.4, "c": 585.4, "v": 1000.0} for t in stamps if start <= t <= end]
            needs = {"symbols": ["SPY"], "bars": {"timeframe": "15Min", "limit": 5}, "structures": True}
            built = store.tape(needs, "2026-09-22T00:00:00Z", "2026-09-22T23:59:59Z", horizon="day", underlier_bars=underlier,
                               execution="15Min", max_option_bars=2)
            self.assertEqual([step["t"] for step in built["steps"]], stamps[1:])
            self.assertEqual(built["bounded"]["option_bars"], 3)
            self.assertEqual(built["warmup_bars"]["SPY"][-1]["t"], stamps[0])  # the dropped step's signal bar is warmup now
            whole = store.tape(needs, "2026-09-22T00:00:00Z", "2026-09-22T23:59:59Z", horizon="day", underlier_bars=underlier, execution="15Min")
            self.assertNotIn("bounded", whole)

    def test_the_faster_implied_volatility_is_the_same_number(self):
        import random

        def slow(price, spot, strike, years, right, low=0.005, high=5.0):
            if not oh.bs_price(spot, strike, years, low, right) < price < oh.bs_price(spot, strike, years, high, right):
                return None
            for _ in range(80):
                mid = 0.5 * (low + high)
                if oh.bs_price(spot, strike, years, mid, right) < price:
                    low = mid
                else:
                    high = mid
                if high - low < 1e-7:
                    break
            return 0.5 * (low + high)
        rng = random.Random(7)
        for _ in range(1500):
            spot = rng.uniform(5, 800)
            args = (rng.uniform(0.01, 0.1 * spot), spot, spot * rng.uniform(0.8, 1.2), rng.uniform(1e-5, 0.1), rng.choice(("call", "put")))
            self.assertEqual(oh.implied_vol(*args), slow(*args))


class StructureKit(unittest.TestCase):
    def test_the_box_replays_a_structure_with_the_kit_alone(self):
        """In the agent's box `replay.py` runs beside its kit and nothing else: no `league`, no `ltcm`."""
        import os
        import subprocess
        import sys
        from league.sandbox import kit_files
        files = kit_files()
        self.assertIn("structure_core.py", files)
        steps = [sstep("2026-09-22T13:45:00Z", VPRICES), sstep("2026-09-22T14:00:00Z", VPRICES)]
        spec = {"code": STRUCTURE_STRATEGY, "params": {"legs": VLEGS, "open_at": "2026-09-22T13:45:00Z", "limit": 0.60},
                "tape": stape(steps, VERTICAL), "stake": 1000.0, "limits": SLIMITS, "token": "t"}
        with tempfile.TemporaryDirectory() as box:
            for name, source in files.items():
                target = Path(box) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(Path(source).read_text(encoding="utf-8"), encoding="utf-8")
            (Path(box) / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
            run = subprocess.run([sys.executable, "-s", "replay.py", "--spec", "spec.json"], cwd=box, env=env, capture_output=True, text=True, timeout=120)
        line = [x for x in run.stdout.splitlines() if x.startswith("REPLAY-RESULT t ")][-1]
        result = json.loads(line[len("REPLAY-RESULT t "):])
        self.assertTrue(result["ok"], result)
        self.assertEqual((result["fills"], result["options"]["structures"]["opened"]), (1, 1))
        self.assertEqual(structure_core.TYPES, ("debit_vertical", "long_butterfly", "calendar", "diagonal", "long_straddle",
                                                "long_strangle", "credit_vertical", "iron_condor", "iron_butterfly"))
