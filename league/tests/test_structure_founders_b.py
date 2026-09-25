"""The structure founders of direction and events (builder S4b of the options-desk run, Sept 25, 2026).

Every founder is tested as it runs: its source through `league.runner.decide(code, ctx)` with a
hand-built ctx whose chain is priced by Black-Scholes, and every intent it returns must be one
`league.structures.parse` accepts (the spec's schema, `docs/runs/2026-09-25-options-desk.md`). Each
founder's entry fires on its own signal and stays out without it; its exits fire (the profit target,
the stop, the time exit); it never opens past the expiry-day entry cut or holds into the close of its
earliest expiry.
"""

import math
import unittest
from datetime import date, datetime, timedelta, timezone

from league import parameters, runner, structures
from league.safety import check_code
from league.seeds import SEEDS, load

FOUNDERS = {
    "options-orb": ("options-orb-vertical", "options_orb.py"),
    "options-trend-vertical": ("options-trend-vertical", "options_trend_vertical.py"),
    "options-reversal": ("options-reversal-vertical", "options_reversal.py"),
    "options-gap-drift": ("options-gap-drift", "options_gap_drift.py"),
    "options-skew": ("options-skew", "options_skew.py"),
    "options-diagonal": ("options-trend-diagonal", "options_diagonal.py"),
}
LIMITS = {"max_position_usd": 100.0, "max_order_usd": 75.0}
SPEC_PARAMS = ("structure", "width", "dte_min", "dte_max", "entry_delta", "profit_target", "stop_loss", "exit_minutes_before_close", "max_open")


# ------------------------------------------------------------------------------------ the market
def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs(spot, strike, years, vol, right):
    """(price, delta) of a European option, no rate: good enough to make a plausible chain."""
    years = max(years, 1.0 / (365 * 24))
    d1 = (math.log(spot / strike) + 0.5 * vol * vol * years) / (vol * math.sqrt(years))
    d2 = d1 - vol * math.sqrt(years)
    if right == "call":
        return spot * ncdf(d1) - strike * ncdf(d2), ncdf(d1)
    return strike * ncdf(-d2) - spot * ncdf(-d1), ncdf(d1) - 1.0


def occ(under, expiry, right, strike):
    return f"{under}{expiry[2:4]}{expiry[5:7]}{expiry[8:10]}{'C' if right == 'call' else 'P'}{int(round(strike * 1000)):08d}"


def chain(under, spot, now, expiries, vol=0.15, step=1.0, span=12, skew=0.0, half=0.01):
    """Chain rows as the House shows them: `span` strikes either side of the money, `step` apart, for each
    expiry; a put under the money trades `skew` over the call volatility (the 25-delta skew the founders read)."""
    rows, moment = [], datetime.fromisoformat(now.replace("Z", "+00:00"))
    for expiry in expiries:
        years = max((datetime.fromisoformat(expiry + "T20:00:00+00:00") - moment).total_seconds() / (365 * 86400), 1e-4)
        base = round(spot / step) * step
        for i in range(-span, span + 1):
            strike = round(base + i * step, 2)
            for right in ("call", "put"):
                v = vol + (skew if right == "put" and strike < spot else 0.0)
                price, delta = bs(spot, strike, years, v, right)
                bid, ask = max(0.0, round(price - half, 2)), round(price + half, 2)
                if ask <= 0.01:
                    continue
                code = occ(under, expiry, right, strike)
                rows.append({"symbol": code, "occ": code, "underlying": under, "expiry": expiry, "strike": strike, "right": right,
                             "bid": bid, "ask": ask, "as_of": now, "iv": v, "delta": round(delta, 4), "volume": 500, "underlying_price": spot})
    return rows


def daily_bars(closes, last_day="2026-09-23"):
    """Closed daily bars stamped at midnight New York after each session (04:00Z in September); the last is
    `last_day`'s, the session before Thursday Sept 24, 2026, the tests' usual today."""
    out, day = [], date.fromisoformat(last_day)
    days = []
    while len(days) < len(closes):
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    for d, (i, c) in zip(reversed(days), enumerate(closes)):
        o = closes[i - 1] if i else c
        out.append({"t": f"{(d + timedelta(days=1)).isoformat()}T04:00:00Z", "o": o, "h": max(o, c) * 1.002, "l": min(o, c) * 0.998, "c": c, "v": 1e6})
    return out


def intraday_bars(day, closes, first_open=None, start_minute=585, step=15):
    """Closed 15-minute bars of `day` (New York is UTC-4), the first closing at 09:45."""
    out = []
    for i, c in enumerate(closes):
        o = (first_open if i == 0 and first_open is not None else closes[i - 1] if i else c)
        minute = start_minute + i * step + 240
        out.append({"t": f"{day}T{minute // 60:02d}:{minute % 60:02d}:00Z", "o": o, "h": max(o, c) + 0.05, "l": min(o, c) - 0.05, "c": c, "v": 1e5})
    return out


def ctx_for(now, chain_rows, bars, positions=(), orders=(), memory=None, params=None, cash=200.0, quotes=None, limits=None):
    q = {s: {"bid": rows[-1]["c"] - 0.01, "ask": rows[-1]["c"] + 0.01, "t": now} for s, rows in bars.items() if rows}
    q.update(quotes or {})
    return {"now": now, "venue": "alpaca", "rung": 1, "params": dict(params or {}), "memory": dict(memory or {}), "cash": cash, "equity": cash,
            "limits": dict(limits or LIMITS), "fees": {"option_per_contract": 0.05}, "positions": list(positions), "open_orders": list(orders),
            "bars": bars, "quotes": q, "chain": list(chain_rows), "structures": []}


def width(intent):
    strikes = [structures.parse("alpaca", intent).spec.legs[i].strike for i in (0, 1)]
    return float(abs(strikes[0] - strikes[1]))


def held(intent, paid, mark, quantity=1, opened_at="2026-09-24T14:00:00Z"):
    """The position row the House shows for a structure opened by `intent`: held price S paid and marked."""
    order = structures.parse("alpaca", {**intent, "action": "open"})
    spec = order.spec
    return {"symbol": spec.underlying, "structure": spec.type, "legs": spec.intent_legs(), "market_id": spec.code, "quantity": quantity,
            "average_cost": paid, "mark": mark, "natural_open": float(structures.natural_price(spec, str(paid))), "expiry": spec.expiry,
            "pnl_usd": round((mark - paid) * 100 * quantity, 2), "opened_at": opened_at, "reason": "test"}


class FounderCase(unittest.TestCase):
    SEED = ""

    @classmethod
    def setUpClass(cls):
        if cls is FounderCase:
            raise unittest.SkipTest("base")
        cls.code = load(cls.SEED)

    def run_seed(self, ctx):
        out = runner.decide(self.code, ctx)
        self.assertTrue(out.get("ok"), out.get("error"))
        self.assertTrue(out["thought"].strip())
        for intent in out["intents"]:
            order = structures.parse("alpaca", intent)  # raises unless the spec's schema admits it
            if order.action == "open":
                self.assertLessEqual(float(order.max_loss_usd), LIMITS["max_order_usd"] + 1e-9)
                self.assertLessEqual(float(order.max_loss_usd), ctx["cash"])
        return out

    def opens(self, out):
        return [i for i in out["intents"] if i["action"] == "open"]

    def closes(self, out):
        return [i for i in out["intents"] if i["action"] == "close"]


# ------------------------------------------------------------------------------- the registry
class RegistryTests(unittest.TestCase):
    def test_six_founders_in_seeds_each_its_own_family(self):
        rows = {row["name"]: row for row in SEEDS}
        for name, (family, filename) in FOUNDERS.items():
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertEqual((rows[name]["family"], rows[name]["file"]), (family, filename))
                self.assertGreater(len(rows[name]["why"]), 40)
        self.assertEqual(len({f for f, _ in FOUNDERS.values()}), len(FOUNDERS))

    def test_safe_short_and_explained(self):
        for name in FOUNDERS:
            with self.subTest(name):
                code = load(name)
                check_code(code)
                lines = code.splitlines()
                self.assertLessEqual(len(lines), 200, "a structure founder carries its own builder and exits: 160 lines (test_seeds) is for single legs")
                self.assertTrue(lines[0].startswith(f"# {name}:"))
                header = "\n".join(line for line in lines[:40] if line.startswith("#"))
                for word in ("THE IDEA", "THE EVIDENCE", "WHAT IT NEEDS", "WHEN IT TRADES", "HOW IT EXITS"):
                    self.assertIn(word, header)
                for banned in ("import random", "import time", "datetime.now", "utcnow", "today()"):
                    self.assertNotIn(banned, code)

    def test_needs_and_params_follow_the_spec(self):
        for name in FOUNDERS:
            with self.subTest(name):
                found = runner.needs_of(load(name))
                self.assertTrue(found["ok"], found.get("error"))
                needs, params = found["needs"], found["params"]
                self.assertEqual((needs["venue"], needs["horizon"], needs["asset_class"]), ("alpaca", "day", "option"))
                self.assertIs(needs["structures"], True)
                self.assertTrue(5 <= needs["wake_minutes"] <= 10)
                self.assertTrue(2 <= needs["max_days_to_expiry"] <= 45 or needs["max_days_to_expiry"] in (0, 1))
                self.assertLessEqual(len(needs["symbols"]), 8)
                self.assertNotIn("feeds", needs, "the options replay tape carries no feeds: a founder that declares one cannot be replayed")
                for key in SPEC_PARAMS:
                    self.assertIn(key, params)
                self.assertIn(params["structure"], structures.TYPES)
                self.assertGreaterEqual(params["notional_usd"], 1.0)
                self.assertLessEqual(params["notional_usd"], LIMITS["max_order_usd"])
                check = parameters.inspect(params, needs)
                self.assertEqual(check["errors"], [])
                for key in ("width", "dte_min", "dte_max", "entry_delta", "profit_target", "stop_loss", "exit_minutes_before_close"):
                    self.assertIn(key, check["mutable"], "the lab and research can move it")

    def test_missing_and_broken_data_never_raises(self):
        junk = [{}, {"now": None, "positions": None, "open_orders": None, "bars": None, "chain": None, "limits": None, "memory": None},
                {"now": "2026-09-24T15:00:00Z", "memory": ["x"], "chain": [None, {}, {"underlying": "SPY", "strike": "x"}]},
                {"now": "2026-09-24T15:00:00Z", "cash": "lots", "bars": {"SPY": [None, {}, {"c": "x"}]}, "positions": [None, {"structure": "debit_vertical"}],
                 "open_orders": [None, {"order_id": 7}]}]
        for name in FOUNDERS:
            for index, ctx in enumerate(junk):
                with self.subTest(founder=name, ctx=index):
                    out = runner.decide(load(name), ctx)
                    self.assertTrue(out.get("ok"), out.get("error"))
                    self.assertEqual(out["intents"], [])


# ------------------------------------------------------------------------------- options-orb
THU, FRI = "2026-09-24", "2026-09-25"  # New York is UTC-4; Sept 24, 2026 is a Thursday


def orb_bars(closes, first_open=280.1, day=THU):
    return {"IWM": intraday_bars(day, closes, first_open=first_open), "BAC": [], "SOFI": [], "SNAP": [], "AAL": []}


class OrbTests(FounderCase):
    SEED = "options-orb"
    UP = [280.0, 280.2, 280.5, 280.8, 281.1, 281.4]  # the range 279.95-280.25 (bars +-0.05), then a breakout up by 11:00

    def ctx(self, now, spot, closes, expiries=(FRI, "2026-09-28"), **more):
        return ctx_for(now, chain("IWM", spot, now, list(expiries), vol=0.18), orb_bars(closes, day=now[:10]), **more)

    def test_fades_a_breakout_by_default_and_rides_it_with_fade_off(self):
        out = self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP))
        [intent] = self.opens(out)
        order = structures.parse("alpaca", intent)
        self.assertEqual((order.spec.type, order.spec.legs[0].right), ("debit_vertical", "put"), "fade 1: a breakout up buys puts")
        self.assertIn("fading it", intent["reason"])
        self.assertLessEqual(float(order.max_loss_usd), 60.0, "notional_usd")
        [ride] = self.opens(self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP, params={"fade": 0})))
        self.assertEqual(structures.parse("alpaca", ride).spec.legs[0].right, "call")
        [credit] = self.opens(self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP, params={"fade": 0, "structure": "credit_vertical"})))
        spec = structures.parse("alpaca", credit).spec
        self.assertEqual((spec.type, spec.legs[0].right), ("credit_vertical", "put"), "the same bullish view as a put credit spread")

    def test_once_a_day_after_the_fill_is_seen(self):
        out = self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP))
        intent = self.opens(out)[0]
        self.assertEqual(out["memory"]["sent"], {"IWM": THU})
        retry = self.run_seed(self.ctx("2026-09-24T15:15:00Z", 281.5, self.UP + [281.5], memory=out["memory"]))
        self.assertEqual(len(self.opens(retry)), 1, "not filled: sent again while the breakout stands")
        seen = self.run_seed(self.ctx("2026-09-24T15:15:00Z", 281.5, self.UP + [281.5], memory=out["memory"], positions=[held(intent, 0.45, 0.45)]))
        self.assertEqual(seen["memory"]["done"], {"IWM": THU})
        again = self.run_seed(self.ctx("2026-09-24T15:30:00Z", 281.6, self.UP + [281.5, 281.6], memory=seen["memory"]))
        self.assertEqual(self.opens(again), [], "the day's breakout is spent once its structure was held")

    def test_no_breakout_no_entry_and_none_outside_the_window(self):
        self.assertEqual(self.opens(self.run_seed(self.ctx("2026-09-24T15:00:00Z", 280.1, [280.0, 280.2, 280.1, 280.0, 280.2, 280.1]))), [])
        self.assertEqual(self.opens(self.run_seed(self.ctx("2026-09-24T17:15:00Z", 281.4, self.UP + [281.4] * 9))), [], "13:15 is past entry_end")

    def test_never_opens_a_structure_expiring_today_after_14_00(self):
        late = self.ctx("2026-09-25T18:05:00Z", 281.4, self.UP + [281.4] * 12, expiries=(FRI,), params={"entry_end": 900})
        self.assertEqual(self.opens(self.run_seed(late)), [])
        early = self.ctx("2026-09-25T16:05:00Z", 281.4, self.UP + [281.4] * 4, expiries=(FRI,))
        self.assertEqual(len(self.opens(self.run_seed(early))), 1, "before 14:00 a 0-day structure is allowed")

    def test_exits_at_the_target_the_stop_the_signal_and_the_time(self):
        intent = self.opens(self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP)))[0]
        bars, top = self.UP + [281.5, 281.6, 281.5, 281.4], round(0.45 + 0.6 * (width(intent) - 0.45), 2)
        [win] = self.closes(self.run_seed(self.ctx("2026-09-24T16:00:00Z", 281.4, bars, positions=[held(intent, 0.45, top)])))
        self.assertIn("target", win["reason"])
        self.assertEqual(win["limit_price"], round(top - 0.02, 2), "a target is taken at the bid less `slip`")
        [stop] = self.closes(self.run_seed(self.ctx("2026-09-24T16:00:00Z", 281.4, bars, positions=[held(intent, 0.45, 0.2)], params={"stop_loss": 0.5})))
        self.assertIn("stop", stop["reason"])
        self.assertEqual(self.closes(self.run_seed(self.ctx("2026-09-24T16:00:00Z", 281.4, bars, positions=[held(intent, 0.45, 0.2)]))), [],
                         "stop_loss 1.0: no stop on the mark")
        back = self.UP + [281.0, 280.6, 280.3, 280.1]
        [done] = self.closes(self.run_seed(self.ctx("2026-09-24T16:00:00Z", 280.1, back, positions=[held(intent, 0.45, 0.55)])))
        self.assertIn("the fade has done its work", done["reason"])
        [flat] = self.closes(self.run_seed(self.ctx("2026-09-24T19:40:00Z", 281.4, self.UP + [281.4] * 23, positions=[held(intent, 0.45, 0.50)])))
        self.assertIn("out before the close", flat["reason"])
        self.assertEqual(flat["limit_price"], 0.01, "the clock's exit takes whatever the bid is")

    def test_on_its_expiry_day_it_is_out_by_15_15(self):
        intent = self.opens(self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP)))[0]
        friday = self.ctx("2026-09-25T19:15:00Z", 281.4, [281.4] * 22, expiries=(FRI,), positions=[held(intent, 0.45, 0.50)], params={"exit_minutes_before_close": 20})
        [flat] = self.closes(self.run_seed(friday))
        self.assertIn("0 days to its first expiry", flat["reason"])

    def test_stale_orders_are_cancelled_and_a_resting_close_is_not_doubled(self):
        intent = self.opens(self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP)))[0]
        position = held(intent, 0.45, round(0.45 + 0.6 * (width(intent) - 0.45), 2))
        resting = {"order_id": "ord-9", "symbol": "IWM", "side": "sell", "quantity": 1, "limit_price": 0.79, "submitted_at": "2026-09-24T15:55:00Z",
                   "market_id": position["market_id"]}
        out = self.run_seed(self.ctx("2026-09-24T16:00:00Z", 281.4, self.UP + [281.4] * 4, positions=[position], orders=[resting]))
        self.assertEqual((out["intents"], out["cancels"]), ([], []))
        stale = self.run_seed(self.ctx("2026-09-24T16:30:00Z", 281.4, self.UP + [281.4] * 6, positions=[position], orders=[resting]))
        self.assertEqual(stale["cancels"], ["ord-9"])
        self.assertEqual(len(self.closes(stale)), 1, "the stale close is cancelled and sent again in one decision")

    def test_respects_the_caps_and_the_cash(self):
        self.assertEqual(self.opens(self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP, cash=10.0))), [])
        full = held(self.opens(self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP)))[0], 0.45, 0.45)
        out = self.run_seed(self.ctx("2026-09-24T15:00:00Z", 281.4, self.UP, positions=[full, dict(full, symbol="BAC")]))
        self.assertEqual(self.opens(out), [], "max_open structures are held")


# ---------------------------------------------------------------------- options-trend-vertical
def rising(n=40, start=700.0, step=1.5):
    return [start + step * i for i in range(n)]


OTHERS = lambda keep, names: {s: [] for s in names if s != keep}  # noqa: E731


class TrendVerticalTests(FounderCase):
    SEED = "options-trend-vertical"
    NOW = "2026-09-24T15:00:00Z"  # Thursday 11:00 New York
    UP = rising(35, 45.0, 0.3) + [55.5, 55.8, 56.0, 56.2, 55.4]  # above a rising 20-day mean; closed yesterday under its 5-day mean

    def ctx(self, closes, price, now=None, **more):
        now = now or self.NOW
        rows = chain("BAC", price, now, ["2026-09-28", "2026-10-02"], vol=0.27, step=0.5)
        bars = {"BAC": daily_bars(closes), **OTHERS("BAC", ("PFE", "T", "SOFI"))}
        return ctx_for(now, rows, bars, quotes={"BAC": {"bid": price - 0.01, "ask": price + 0.01}}, **more)

    def test_buys_a_call_vertical_on_a_pullback_in_an_uptrend(self):
        [intent] = self.opens(self.run_seed(self.ctx(self.UP, 55.8)))
        spec = structures.parse("alpaca", intent).spec
        self.assertEqual((spec.type, spec.legs[0].right, spec.expiry), ("debit_vertical", "call", "2026-09-28"))

    def test_no_pullback_or_no_trend_no_entry(self):
        self.assertEqual(self.opens(self.run_seed(self.ctx(rising(40, 45.0, 0.3), 57.0))), [], "an uptrend without a pullback")
        self.assertEqual(self.opens(self.run_seed(self.ctx([56.0 + (0.1 if i % 2 else -0.1) for i in range(40)], 56.0))), [], "no trend")

    def test_downtrends_only_with_both_sides(self):
        down = [68.0 - 0.3 * i for i in range(35)] + [57.5, 57.2, 57.0, 56.8, 57.6]
        self.assertEqual(self.opens(self.run_seed(self.ctx(down, 57.2))), [])
        [intent] = self.opens(self.run_seed(self.ctx(down, 57.2, params={"both_sides": 1})))
        self.assertEqual(structures.parse("alpaca", intent).spec.legs[0].right, "put")

    def test_exits_target_trend_break_hold_and_expiry_day(self):
        intent = self.opens(self.run_seed(self.ctx(self.UP, 55.8)))[0]
        top = round(0.3 + 0.7 * (width(intent) - 0.3), 2)
        self.assertIn("target", self.closes(self.run_seed(self.ctx(self.UP, 56.5, positions=[held(intent, 0.3, top)])))[0]["reason"])
        self.assertIn("crossed", self.closes(self.run_seed(self.ctx(self.UP, 50.0, positions=[held(intent, 0.3, 0.1)])))[0]["reason"])
        old = held(intent, 0.3, 0.3, opened_at="2026-09-20T14:00:00Z")
        self.assertIn("held 4 days", self.closes(self.run_seed(self.ctx(self.UP, 55.8, positions=[old])))[0]["reason"])
        self.assertEqual(self.closes(self.run_seed(self.ctx(self.UP, 55.8, positions=[held(intent, 0.3, 0.3)]))), [])
        monday = self.ctx(self.UP, 55.8, now="2026-09-28T19:00:00Z", positions=[held(intent, 0.3, 0.3, opened_at="2026-09-28T14:00:00Z")])
        [flat] = self.closes(self.run_seed(monday))
        self.assertIn("0 days to its first expiry", flat["reason"])


# ----------------------------------------------------------------------------- options-reversal
CALM = [280.0 * (1 + (0.006 if i % 2 else -0.006)) for i in range(30)]
REV = ("BAC", "SOFI", "AAL", "CCL", "RIVN")


class ReversalTests(FounderCase):
    SEED = "options-reversal"

    def ctx(self, closes, price, now="2026-09-24T18:45:00Z", **more):  # 14:45 New York
        rows = chain("IWM", price, now, ["2026-09-28", "2026-10-02"], vol=0.18)
        bars = {"IWM": daily_bars(closes), **{s: [] for s in REV}}
        return ctx_for(now, rows, bars, quotes={"IWM": {"bid": price - 0.01, "ask": price + 0.01}}, **more)

    def test_buys_calls_after_a_drop_and_fades_a_spike_only_with_fade_up(self):
        [up] = self.opens(self.run_seed(self.ctx(CALM, CALM[-1] * 0.98)))
        self.assertEqual(structures.parse("alpaca", up).spec.legs[0].right, "call")
        self.assertEqual(self.opens(self.run_seed(self.ctx(CALM, CALM[-1] * 1.02))), [])
        [down] = self.opens(self.run_seed(self.ctx(CALM, CALM[-1] * 1.02, params={"fade_up": 1})))
        self.assertEqual(structures.parse("alpaca", down).spec.legs[0].right, "put")
        self.assertEqual(self.opens(self.run_seed(self.ctx(CALM, CALM[-1] * 0.998))), [], "an ordinary day")
        self.assertEqual(self.opens(self.run_seed(self.ctx(CALM, CALM[-1] * 0.98, now="2026-09-24T16:00:00Z"))), [], "12:00 is outside both windows")

    def test_fades_yesterdays_drop_next_morning_once(self):
        crash = CALM + [CALM[-1] * 0.975]
        first = self.run_seed(self.ctx(CALM, CALM[-1] * 0.975))  # the late-day entry, Thursday
        self.assertEqual(len(self.opens(first)), 1)
        again = self.run_seed(self.ctx(CALM, CALM[-1] * 0.975, now="2026-09-24T19:15:00Z", memory=first["memory"]))
        self.assertEqual(len(self.opens(again)), 1, "an entry that did not fill is sent again while the move stands")
        filled = self.run_seed(self.ctx(CALM, CALM[-1] * 0.975, now="2026-09-24T19:20:00Z", memory=first["memory"], positions=[held(self.opens(first)[0], 0.45, 0.45)]))
        self.assertEqual(filled["memory"]["done"], {"IWM": first["memory"]["sent"]["IWM"]}, "seen held: the event is spent")
        friday = self.ctx(crash, crash[-1], now="2026-09-25T14:15:00Z", memory=filled["memory"])
        friday["bars"]["IWM"] = daily_bars(crash, last_day="2026-09-24")
        self.assertEqual(self.opens(self.run_seed(friday)), [], "one entry an event")
        fresh = self.ctx(crash, crash[-1], now="2026-09-25T14:15:00Z")
        fresh["bars"]["IWM"] = daily_bars(crash, last_day="2026-09-24")
        self.assertEqual(len(self.opens(self.run_seed(fresh))), 1, "without the memory, yesterday's drop is bought in the morning")

    def test_exits_when_the_drop_is_made_back_and_after_max_hold(self):
        first = self.run_seed(self.ctx(CALM, CALM[-1] * 0.98))
        intent = self.opens(first)[0]
        back = self.ctx(CALM, CALM[-1] + 1.0, now="2026-09-25T14:15:00Z", positions=[held(intent, 0.45, 0.50)], memory=first["memory"])
        self.assertIn("reversed", self.closes(self.run_seed(back))[0]["reason"])
        old = self.ctx(CALM, CALM[-1] * 0.98, now="2026-09-25T14:15:00Z", positions=[held(intent, 0.45, 0.45, opened_at="2026-09-21T19:00:00Z")])
        self.assertIn("held 4 days", self.closes(self.run_seed(old))[0]["reason"])


# ---------------------------------------------------------------------------- options-gap-drift
QUIET = [25.0 * (1 + (0.01 if i % 2 else -0.01)) for i in range(30)]


class GapDriftTests(FounderCase):
    SEED = "options-gap-drift"

    def ctx(self, closes, price, now="2026-09-24T14:30:00Z", **more):  # 10:30 New York
        rows = chain("T", price, now, ["2026-09-28", "2026-10-02"], vol=0.3, step=0.5)
        bars = {"T": daily_bars(closes), **{s: [] for s in ("BAC", "F", "AAL", "RIVN", "CCL")}}
        return ctx_for(now, rows, bars, quotes={"T": {"bid": price - 0.01, "ask": price + 0.01}}, **more)

    def test_rides_a_gap_up_with_calls_and_a_gap_down_with_puts(self):
        [up] = self.opens(self.run_seed(self.ctx(QUIET, QUIET[-1] * 1.07)))
        self.assertEqual(structures.parse("alpaca", up).spec.legs[0].right, "call")
        [down] = self.opens(self.run_seed(self.ctx(QUIET, QUIET[-1] * 0.93)))
        self.assertEqual(structures.parse("alpaca", down).spec.legs[0].right, "put")
        self.assertEqual(self.opens(self.run_seed(self.ctx(QUIET, QUIET[-1] * 1.015))), [], "an ordinary day")
        self.assertEqual(self.opens(self.run_seed(self.ctx(QUIET, QUIET[-1] * 1.07, now="2026-09-24T16:30:00Z"))), [], "after 12:00")

    def test_the_day_after_only_if_today_has_not_undone_it(self):
        gapped = QUIET + [QUIET[-1] * 1.07]
        self.assertEqual(len(self.opens(self.run_seed(self.ctx(gapped, gapped[-1] * 1.005)))), 1)
        self.assertEqual(self.opens(self.run_seed(self.ctx(gapped, gapped[-1] * 0.995))), [])

    def test_exits_when_the_gap_fills(self):
        first = self.run_seed(self.ctx(QUIET, QUIET[-1] * 1.07))
        intent = self.opens(first)[0]
        filled = self.ctx(QUIET, QUIET[-1] * 0.99, positions=[held(intent, 0.3, 0.1)], memory=first["memory"], now="2026-09-24T15:30:00Z")
        self.assertIn("gap filled", self.closes(self.run_seed(filled))[0]["reason"])


# --------------------------------------------------------------------------------- options-skew
class SkewTests(FounderCase):
    SEED = "options-skew"
    NOW = "2026-09-24T15:00:00Z"

    def ctx(self, skew, closes=None, price=761.0, **more):
        rows = chain("SPY", price, self.NOW, ["2026-09-28", "2026-10-02"], vol=0.13, skew=skew)
        return ctx_for(self.NOW, rows, {"SPY": daily_bars(closes or rising(30, 716.0)), "QQQ": [], "IWM": []},
                       quotes={"SPY": {"bid": price - 0.01, "ask": price + 0.01}}, **more)

    def test_cheap_skew_rides_the_calm_with_calls_or_buys_puts(self):
        out = self.run_seed(self.ctx(0.0))
        [intent] = self.opens(out)
        order = structures.parse("alpaca", intent)
        self.assertEqual((order.spec.type, order.spec.legs[0].right), ("debit_vertical", "call"))
        self.assertLessEqual(float(order.max_loss_usd), 72.0)
        self.assertEqual(len(out["memory"]["skew"]["SPY"]), 1, "the day's reading is kept")
        [puts] = self.opens(self.run_seed(self.ctx(0.0, params={"cheap_side": -1})))
        self.assertEqual(structures.parse("alpaca", puts).spec.legs[0].right, "put")
        self.assertEqual(self.opens(self.run_seed(self.ctx(0.0, params={"cheap_side": 0}))), [])

    def test_rich_skew_sells_a_put_credit_vertical_only_when_asked_and_above_the_trend(self):
        self.assertEqual(self.opens(self.run_seed(self.ctx(0.09))), [], "rich_side 0 by default")
        [intent] = self.opens(self.run_seed(self.ctx(0.09, params={"rich_side": 1})))
        order = structures.parse("alpaca", intent)
        self.assertEqual((order.spec.type, order.spec.legs[0].right), ("credit_vertical", "put"))
        self.assertEqual(self.opens(self.run_seed(self.ctx(0.09, closes=[800.0 - i for i in range(30)], params={"rich_side": 1}))), [],
                         "rich, but the index is under its mean")

    def test_its_own_history_replaces_the_norm(self):
        reading = self.run_seed(self.ctx(0.0))["memory"]["skew"]["SPY"][0][1]
        history = {"skew": {"SPY": [[date(2026, 9, d).toordinal(), reading] for d in range(10, 20)]}}
        self.assertEqual(self.opens(self.run_seed(self.ctx(0.0, memory=history))), [], "cheap against the norm, ordinary against its own days")

    def test_credit_exits_at_half_the_credit_and_at_the_stop(self):
        intent = self.opens(self.run_seed(self.ctx(0.09, params={"rich_side": 1})))[0]
        k = width(intent)
        paid = round(k - intent["limit_price"], 2)  # held at K less the credit
        [close] = self.closes(self.run_seed(self.ctx(0.09, positions=[held(intent, paid, round(paid + 0.6 * intent["limit_price"], 2))])))
        self.assertIn("target", close["reason"])
        self.assertLess(structures.parse("alpaca", close).held_limit, k)
        lose = self.run_seed(self.ctx(0.09, positions=[held(intent, paid, round(paid - 1.05 * intent["limit_price"], 2))]))
        self.assertIn("stop", self.closes(lose)[0]["reason"])


# ----------------------------------------------------------------------------- options-diagonal
class DiagonalTests(FounderCase):
    SEED = "options-diagonal"
    NOW = "2026-09-24T15:00:00Z"

    def ctx(self, closes, price, now=None, **more):
        now = now or self.NOW
        rows = chain("BAC", price, now, ["2026-09-25", "2026-09-28", "2026-10-02"], vol=0.27, step=0.5, span=10)
        bars = {"BAC": daily_bars(closes), **{s: [] for s in ("PFE", "T", "F", "AAL", "SNAP")}}
        return ctx_for(now, rows, bars, quotes={"BAC": {"bid": price - 0.01, "ask": price + 0.01}}, **more)

    def test_a_call_diagonal_in_an_uptrend(self):
        [intent] = self.opens(self.run_seed(self.ctx(rising(30, 50.0, 0.2), 56.0)))
        spec = structures.parse("alpaca", intent).spec
        long, short = [leg for leg in spec.legs if leg.sign > 0][0], [leg for leg in spec.legs if leg.sign < 0][0]
        self.assertEqual((spec.type, long.right), ("diagonal", "call"))
        self.assertLess(short.expiry, long.expiry)
        self.assertLessEqual(long.strike, short.strike - structures.money("0.5"))
        self.assertEqual(spec.expiry, short.expiry, "its clock is the near leg")

    def test_no_trend_no_entry_and_downtrends_only_with_both_sides(self):
        self.assertEqual(self.opens(self.run_seed(self.ctx([56.0 + (0.1 if i % 2 else -0.1) for i in range(30)], 56.0))), [])
        down = [62.0 - 0.2 * i for i in range(30)]
        self.assertEqual(self.opens(self.run_seed(self.ctx(down, 55.5))), [])
        [intent] = self.opens(self.run_seed(self.ctx(down, 55.5, params={"both_sides": 1})))
        self.assertEqual(structures.parse("alpaca", intent).spec.legs[0].right, "put")

    def test_exits_at_the_target_and_before_the_near_expiry(self):
        intent = self.opens(self.run_seed(self.ctx(rising(30, 50.0, 0.2), 56.0)))[0]
        paid = intent["limit_price"]
        self.assertIn("target", self.closes(self.run_seed(self.ctx(rising(30, 50.0, 0.2), 56.5, positions=[held(intent, paid, paid * 1.5)])))[0]["reason"])
        self.assertEqual(self.closes(self.run_seed(self.ctx(rising(30, 50.0, 0.2), 56.0, positions=[held(intent, paid, paid)]))), [])
        spec = structures.parse("alpaca", intent).spec
        day = datetime.fromisoformat(spec.expiry + "T18:05:00+00:00").strftime("%Y-%m-%dT%H:%M:%SZ")  # 14:05 New York on the near expiry
        [flat] = self.closes(self.run_seed(self.ctx(rising(30, 50.0, 0.2), 56.0, now=day, positions=[held(intent, paid, paid)])))
        self.assertIn("0 days to its first expiry", flat["reason"])
