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
        # marked at the estimated bid: last print 0.40 less max(1 tick, 4%, half the median range 0.04/0.02)
        self.assertAlmostEqual(result["final_equity"], 1000 - 40.05 + (0.40 - 0.02) * 100, places=6)

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

    def test_a_thin_bar_does_not_fill_beyond_its_volume(self):
        result = run([step("2026-03-02T15:00:00Z", {C1: bar(0.40, 0.42, 0.38, 0.40)}),
                      step("2026-03-02T15:15:00Z", {C1: bar(0.40, 0.41, 0.30, 0.40, v=6, n=3)})],
                     occ=C1, buy_at="2026-03-02T15:00:00Z", limit=0.40)
        self.assertEqual(result["fills"], 0)  # one contract is more than 10% of six
        self.assertEqual(result["options"]["liquidity_misses"], 1)

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

    def __init__(self, days, fail_once=None):
        self.days, self.calls, self.fail_once = days, [], set(fail_once or ())

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

    def test_the_switch_turns_it_off(self):
        self.house.options_history = CoveredStore()
        self.house.settings.options_replay = False
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
