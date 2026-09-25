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
    expiry; a put's volatility is raised by `skew` x its distance under the money in sd (a smile)."""
    rows, moment = [], datetime.fromisoformat(now.replace("Z", "+00:00"))
    for expiry in expiries:
        years = max((datetime.fromisoformat(expiry + "T20:00:00+00:00") - moment).total_seconds() / (365 * 86400), 1e-4)
        base = round(spot / step) * step
        for i in range(-span, span + 1):
            strike = round(base + i * step, 2)
            for right in ("call", "put"):
                v = vol + (skew * max(0.0, (spot - strike) / (spot * vol * math.sqrt(years))) if right == "put" else 0.0)
                price, delta = bs(spot, strike, years, v, right)
                bid, ask = max(0.0, round(price - half, 2)), round(price + half, 2)
                if ask <= 0.01:
                    continue
                code = occ(under, expiry, right, strike)
                rows.append({"symbol": code, "occ": code, "underlying": under, "expiry": expiry, "strike": strike, "right": right,
                             "bid": bid, "ask": ask, "as_of": now, "iv": v, "delta": round(delta, 4), "volume": 500, "underlying_price": spot})
    return rows


def daily_bars(closes, last_day="2026-09-24"):
    """Closed daily bars stamped at midnight New York after each session (04:00Z in September)."""
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


def orb_bars(closes, first_open=760.2):
    return {"SPY": intraday_bars(THU, closes, first_open=first_open), "QQQ": [], "IWM": []}


class OrbTests(FounderCase):
    SEED = "options-orb"
    UP = [760.0, 760.5, 760.8, 761.2, 761.6, 762.0]  # the range 760.0-760.5 (bars +-0.05), then a breakout up by 11:00

    def test_buys_a_call_debit_vertical_on_a_breakout_up(self):
        out = self.run_seed(ctx_for("2026-09-24T15:00:00Z", chain("SPY", 762.0, "2026-09-24T15:00:00Z", [FRI, "2026-09-28"], vol=0.13), orb_bars(self.UP)))
        [intent] = self.opens(out)
        order = structures.parse("alpaca", intent)
        self.assertEqual((order.spec.type, order.spec.legs[0].right), ("debit_vertical", "call"))
        self.assertEqual(order.spec.legs[1].strike - order.spec.legs[0].strike, 1)
        self.assertEqual(out["memory"]["done"], {"SPY": THU})
        again = self.run_seed(ctx_for("2026-09-24T15:15:00Z", chain("SPY", 762.0, "2026-09-24T15:15:00Z", [FRI], vol=0.13), orb_bars(self.UP + [762.2]),
                                      memory=out["memory"]))
        self.assertEqual(self.opens(again), [], "once an underlying a day")

    def test_a_breakout_down_buys_a_put_vertical_and_a_credit_structure_param_sells_calls(self):
        down = [760.0, 760.5, 760.1, 759.6, 759.0, 758.4]
        rows = chain("SPY", 758.4, "2026-09-24T15:00:00Z", [FRI], vol=0.13)
        [intent] = self.opens(self.run_seed(ctx_for("2026-09-24T15:00:00Z", rows, orb_bars(down))))
        self.assertEqual(structures.parse("alpaca", intent).spec.legs[0].right, "put")
        [credit] = self.opens(self.run_seed(ctx_for("2026-09-24T15:00:00Z", rows, orb_bars(down), params={"structure": "credit_vertical"})))
        spec = structures.parse("alpaca", credit).spec
        self.assertEqual((spec.type, spec.legs[0].right), ("credit_vertical", "call"))

    def test_no_breakout_no_entry_and_no_entry_outside_the_window(self):
        rows = chain("SPY", 760.3, "2026-09-24T15:00:00Z", [FRI], vol=0.13)
        self.assertEqual(self.opens(self.run_seed(ctx_for("2026-09-24T15:00:00Z", rows, orb_bars([760.0, 760.5, 760.3, 760.2, 760.4, 760.3])))), [])
        late = self.run_seed(ctx_for("2026-09-24T17:15:00Z", chain("SPY", 762.0, "2026-09-24T17:15:00Z", [FRI], vol=0.13), orb_bars(self.UP + [762.0] * 9)))
        self.assertEqual(self.opens(late), [], "13:15 New York is past entry_end")

    def test_never_opens_a_structure_expiring_today_after_14_00(self):
        rows = chain("SPY", 762.0, "2026-09-25T18:05:00Z", [FRI], vol=0.13)
        bars = {"SPY": intraday_bars(FRI, self.UP + [762.0] * 12, first_open=760.2), "QQQ": [], "IWM": []}
        out = self.run_seed(ctx_for("2026-09-25T18:05:00Z", rows, bars, params={"entry_end": 900}))
        self.assertEqual(self.opens(out), [])
        early = self.run_seed(ctx_for("2026-09-25T16:05:00Z", chain("SPY", 762.0, "2026-09-25T16:05:00Z", [FRI], vol=0.13), bars))
        self.assertEqual(len(self.opens(early)), 1, "before 14:00 a 0-day structure is allowed")

    def vertical(self, now="2026-09-24T15:00:00Z"):
        out = self.run_seed(ctx_for(now, chain("SPY", 762.0, now, [FRI], vol=0.13), orb_bars(self.UP)))
        return self.opens(out)[0]

    def test_exits_at_the_target_the_stop_and_the_time(self):
        intent = self.vertical()
        now, rows = "2026-09-24T16:00:00Z", chain("SPY", 763.0, "2026-09-24T16:00:00Z", [FRI], vol=0.13)
        bars = orb_bars(self.UP + [762.5, 762.8, 763.0, 763.0])
        [win] = self.closes(self.run_seed(ctx_for(now, rows, bars, positions=[held(intent, 0.45, 0.76)])))
        self.assertIn("target", win["reason"])
        self.assertEqual(win["limit_price"], 0.76)
        [stop] = self.closes(self.run_seed(ctx_for(now, rows, bars, positions=[held(intent, 0.45, 0.20)])))
        self.assertIn("stop", stop["reason"])
        self.assertEqual(self.closes(self.run_seed(ctx_for(now, rows, bars, positions=[held(intent, 0.45, 0.50)]))), [], "inside both lines it holds")
        late = self.run_seed(ctx_for("2026-09-24T19:40:00Z", rows, orb_bars(self.UP + [763.0] * 23), positions=[held(intent, 0.45, 0.50)]))
        [flat] = self.closes(late)
        self.assertIn("out before the close", flat["reason"])

    def test_on_its_expiry_day_it_is_out_by_15_15(self):
        intent = self.vertical()
        bars = {"SPY": intraday_bars(FRI, [762.0] * 22, first_open=762.0), "QQQ": [], "IWM": []}
        rows = chain("SPY", 762.0, "2026-09-25T19:15:00Z", [FRI], vol=0.13)
        [flat] = self.closes(self.run_seed(ctx_for("2026-09-25T19:15:00Z", rows, bars, positions=[held(intent, 0.45, 0.50)], params={"exit_minutes_before_close": 20})))
        self.assertIn("0 days to its first expiry", flat["reason"])

    def test_a_failed_breakout_is_closed(self):
        intent = self.vertical()
        rows = chain("SPY", 760.1, "2026-09-24T16:00:00Z", [FRI], vol=0.13)
        [out] = self.closes(self.run_seed(ctx_for("2026-09-24T16:00:00Z", rows, orb_bars(self.UP + [761.0, 760.5, 760.2, 760.1]), positions=[held(intent, 0.45, 0.40)])))
        self.assertIn("breakout failed", out["reason"])

    def test_stale_orders_are_cancelled_and_a_resting_close_is_not_doubled(self):
        intent = self.vertical()
        position = held(intent, 0.45, 0.80)
        resting = {"order_id": "ord-9", "symbol": "SPY", "side": "sell", "quantity": 1, "limit_price": 0.79, "submitted_at": "2026-09-24T15:55:00Z",
                   "market_id": position["market_id"]}
        rows, bars = chain("SPY", 763.0, "2026-09-24T16:00:00Z", [FRI], vol=0.13), orb_bars(self.UP + [763.0] * 4)
        out = self.run_seed(ctx_for("2026-09-24T16:00:00Z", rows, bars, positions=[position], orders=[resting]))
        self.assertEqual((out["intents"], out["cancels"]), ([], []))
        stale = self.run_seed(ctx_for("2026-09-24T16:30:00Z", rows, bars, positions=[position], orders=[resting]))
        self.assertEqual(stale["cancels"], ["ord-9"])
        self.assertEqual(len(self.closes(stale)), 1, "the stale close is cancelled and sent again in one decision")

    def test_respects_the_caps_and_the_cash(self):
        rows = chain("SPY", 762.0, "2026-09-24T15:00:00Z", [FRI], vol=0.13)
        self.assertEqual(self.opens(self.run_seed(ctx_for("2026-09-24T15:00:00Z", rows, orb_bars(self.UP), cash=20.0))), [])
        full = held(self.vertical(), 0.45, 0.45)
        out = self.run_seed(ctx_for("2026-09-24T15:00:00Z", rows, orb_bars(self.UP), positions=[full, dict(full, symbol="QQQ")]))
        self.assertEqual(self.opens(out), [], "max_open structures are held")
