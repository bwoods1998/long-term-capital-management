"""The S4a structure founders (volatility and premium), tested exactly as they run: every decision goes
through `league.runner.decide(code, ctx)` with a hand-built `ctx` -- a Black-Scholes chain around a
chosen spot and implied volatility, and regular-session bars with a chosen realized volatility -- and
every intent they return must be accepted by `league.structures.parse`, the House's one parser.

What each founder must do (the options-desk run, Sept 25, 2026): pass `league.safety.check_code`;
return well-formed structure intents; enter only on its own signal and inside its entry window; fire
its exits (the profit target, the stop and the time exit); never open past the entry cut and never
hold into the close of its earliest expiry."""

import math
import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from league import parameters, runner, structures
from league.safety import check_code
from league.seeds import SEEDS, load

NY = ZoneInfo("America/New_York")
LIMITS = {"max_position_usd": 100.0, "max_order_usd": 75.0}
S4A = ("options-condor-vrp", "options-putspread-dip", "options-ironfly-quiet", "options-strangle-cheap",
       "options-calendar-term", "options-butterfly-pin")


# ------------------------------------------------------------------------------ a synthetic market
def utc(ny_text):
    """'2026-09-25 10:30' New York as an ISO UTC stamp."""
    moment = datetime.strptime(ny_text, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs(spot, strike, years, vol, right):
    if years <= 0:
        return max(0.0, spot - strike if right == "call" else strike - spot)
    sq = vol * math.sqrt(years)
    d1 = (math.log(spot / strike) + 0.5 * vol * vol * years) / sq
    d2 = d1 - sq
    return spot * ncdf(d1) - strike * ncdf(d2) if right == "call" else strike * ncdf(-d2) - spot * ncdf(-d1)


def occ(symbol, expiry, right, strike):
    return f"{symbol}{expiry[2:4]}{expiry[5:7]}{expiry[8:10]}{'C' if right == 'call' else 'P'}{int(round(strike * 1000)):08d}"


def chain(symbol, spot, now_ny, expiries, *, vol=0.18, step=1.0, span=25, half=0.01, vols=None, volume=None):
    """Two-sided rows priced by Black-Scholes at `vol` (or `vols[expiry]`), `half` either side of the
    value (at least a cent), strikes every `step` within `span` of the spot."""
    now = datetime.strptime(now_ny, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
    rows = []
    centre = round(spot / step) * step
    for expiry in expiries:
        close = datetime.strptime(expiry, "%Y-%m-%d").replace(hour=16, tzinfo=NY)
        years = max(0.0, (close - now).total_seconds() / (365.0 * 86400.0))
        sigma = (vols or {}).get(expiry, vol)
        for i in range(-int(span / step), int(span / step) + 1):
            strike = round(centre + i * step, 3)
            for right in ("call", "put"):
                value = bs(spot, strike, years, sigma, right)
                bid, ask = round(max(0.0, value - half), 2), round(max(0.01, value + half), 2)
                if ask <= bid:
                    ask = round(bid + 0.01, 2)
                d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * years) / (sigma * math.sqrt(years)) if years > 0 else 0.0
                code = occ(symbol, expiry, right, strike)
                rows.append({"symbol": code, "occ": code, "underlying": symbol, "expiry": expiry, "strike": strike, "right": right,
                             "bid": bid, "ask": ask, "as_of": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "iv": sigma,
                             "delta": round(ncdf(d1) if right == "call" else ncdf(d1) - 1.0, 4),
                             "volume": (volume or {}).get((strike, right), 100), "underlying_price": spot})
    return rows


def bars(spot, now_ny, *, sessions=8, annual_vol=0.10, minutes=15, today_path=None, trend=0.0):
    """Close-stamped regular-session bars ending at `now_ny`: past sessions alternate up and down by
    the per-bar move `annual_vol` implies (so the realized volatility is what was asked) on a drift of
    `trend` a bar, ending at the spot; today's bars follow `today_path` (prices at each bar, the last
    one the spot) or stay flat at the spot."""
    now = datetime.strptime(now_ny, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
    per_bar = annual_vol / math.sqrt(252 * 390 / minutes)
    count = int(390 / minutes)
    days, day = [], now.date()
    while len(days) < sessions:
        day = day - timedelta(days=1)
        if day.weekday() < 5:
            days.append(day)
    days.reverse()
    t_open = datetime(now.year, now.month, now.day, 9, 30, tzinfo=NY)
    today_count = max(0, int((now - t_open).total_seconds() // (minutes * 60)))
    path = list(today_path or [])[-today_count:] if today_count else []
    if today_count and not path:
        path = [spot] * today_count
    first_today = path[0] if path else spot
    out, price = [], first_today * math.exp(-trend * sessions * count)
    for d in days:
        t = datetime(d.year, d.month, d.day, 9, 30, tzinfo=NY)
        for j in range(count):
            new = price * math.exp((per_bar if j % 2 == 0 else -per_bar) + trend)
            t = t + timedelta(minutes=minutes)
            out.append({"t": t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "o": price, "h": max(price, new) * 1.0001,
                        "l": min(price, new) * 0.9999, "c": new, "v": 1000})
            price = new
    t = t_open
    for j, value in enumerate(path):
        t = t + timedelta(minutes=minutes)
        before = path[j - 1] if j else price
        out.append({"t": t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "o": before, "h": max(before, value) * 1.0001,
                    "l": min(before, value) * 0.9999, "c": value, "v": 1000})
    return out


def ctx_for(now_ny, rows, bar_map, *, positions=(), orders=(), cash=200.0, params=None, memory=None, limits=None):
    return {"now": utc(now_ny), "venue": "alpaca", "rung": 1, "params": dict(params or {}), "memory": dict(memory or {}),
            "cash": cash, "equity": 200.0, "limits": dict(limits or LIMITS), "fees": {"option_per_contract": 0.05},
            "positions": list(positions), "open_orders": list(orders), "bars": bar_map,
            "quotes": {s: {"bid": b[-1]["c"] * 0.9999, "ask": b[-1]["c"] * 1.0001, "t": utc(now_ny)} for s, b in bar_map.items() if b},
            "chain": list(rows)}


def held(intent, paid_held, quantity=1, opened_ny="2026-09-25 10:00", mark=None):
    """A position row for a structure as the House shows it (the spec, section 5)."""
    order = structures.parse("alpaca-paper", intent)
    spec = order.spec
    k = float(spec.collateral)
    return {"symbol": spec.underlying, "occ": spec.code, "market_id": spec.code, "structure": spec.type,
            "legs": spec.intent_legs(), "quantity": quantity, "average_cost": paid_held,
            "mark": paid_held if mark is None else mark, "natural_open": (k - paid_held) if spec.credit else paid_held,
            "pnl_usd": 0.0, "expiry": spec.expiry, "opened_at": utc(opened_ny), "reason": "test"}


class FounderCase(unittest.TestCase):
    SEED = ""

    def run_seed(self, ctx):
        out = runner.decide(load(self.SEED), ctx)
        self.assertTrue(out.get("ok"), out.get("error"))
        self.assertTrue(out["thought"].strip())
        self.assertLessEqual(len(out["intents"]), 8)
        for intent in out["intents"]:
            order = structures.parse("alpaca-paper", intent)  # raises on anything the House would refuse
            if order.action == "open":
                self.assertLessEqual(float(order.max_loss_usd), min(ctx["limits"].values()) + 1e-9, intent)
                self.assertLessEqual(float(order.max_loss_usd), ctx["cash"], intent)
        return out

    def opens(self, out):
        return [i for i in out["intents"] if i.get("action") == "open"]

    def closes(self, out):
        return [i for i in out["intents"] if i.get("action") == "close"]


# ------------------------------------------------------------------------------ every founder
class EveryFounder(unittest.TestCase):
    def test_each_is_registered_with_its_own_family_and_passes_the_safety_check(self):
        rows = {row["name"]: row for row in SEEDS}
        families = set()
        for name in S4A:
            with self.subTest(name=name):
                self.assertIn(name, rows)
                code = load(name)
                check_code(code)
                found = runner.needs_of(code)
                self.assertTrue(found["ok"], found)
                needs, params = found["needs"], found["params"]
                self.assertIs(needs.get("structures"), True)
                self.assertEqual(needs.get("asset_class"), "option")
                self.assertEqual(needs.get("venue"), "alpaca")
                self.assertEqual(needs.get("horizon"), "day")
                for key in ("structure", "width", "dte_min", "dte_max", "entry_delta", "profit_target", "stop_loss",
                            "exit_minutes_before_close", "max_open"):
                    self.assertIn(key, params)
                parameters.require_valid(params, needs)
                self.assertIn(params["structure"], structures.TYPES)
                families.add(rows[name]["family"])
        self.assertEqual(len(families), len(S4A), "one family a founder")

    def test_broken_or_missing_data_never_raises_and_never_trades(self):
        junk = [
            {},
            {"now": None, "positions": None, "open_orders": None, "bars": None, "quotes": None, "chain": None, "limits": None, "memory": None},
            {"now": utc("2026-09-25 11:00"), "memory": ["not", "a", "dict"], "chain": [None, {}, {"occ": "SPY"}, {"occ": "SPY260925C00760000", "bid": "x"}]},
            {"now": "not a time", "cash": "lots", "bars": {"SPY": [None, {}, {"c": "x"}], "QQQ": "nope"},
             "positions": [None, {"structure": "iron_condor"}, {"structure": "iron_condor", "legs": [{"occ": "bad"}], "quantity": 1}],
             "open_orders": [None, {"order_id": 7}]},
            ctx_for("2026-09-25 11:00", [], {"SPY": [], "QQQ": [], "IWM": []}),
        ]
        for name in S4A:
            for index, ctx in enumerate(junk):
                with self.subTest(seed=name, ctx=index):
                    out = runner.decide(load(name), ctx)
                    self.assertTrue(out.get("ok"), out.get("error"))
                    self.assertEqual(out["intents"], [])
                    self.assertTrue(out["thought"].strip())

    def test_no_founder_reads_the_wall_clock_or_draws_random_numbers(self):
        for name in S4A:
            for banned in ("import random", "import time", "datetime.now", "utcnow", "today()"):
                self.assertNotIn(banned, load(name), name)


# ------------------------------------------------------------------------------ the condor
FRI = "2026-09-25"
MON = "2026-09-28"


class CondorVrp(FounderCase):
    SEED = "options-condor-vrp"

    def market(self, now, *, iv=0.30, rv=0.10, spot=760.0):
        return ctx_for(now, chain("SPY", spot, now, [FRI, MON], vol=iv), {"SPY": bars(spot, now, annual_vol=rv), "QQQ": [], "IWM": []})

    def test_sells_a_condor_when_the_implied_move_is_rich_against_the_realized(self):
        out = self.run_seed(self.market(f"{FRI} 10:30"))
        opens = self.opens(out)
        self.assertEqual(len(opens), 1, out["thought"])
        order = structures.parse("alpaca-paper", opens[0])
        self.assertEqual(order.spec.type, "iron_condor")
        self.assertEqual(order.spec.expiry, FRI)  # 0-2 days: Monday's is three days out
        self.assertTrue(order.spec.credit)
        self.assertEqual(float(order.spec.collateral), 1.0)
        self.assertLessEqual(float(order.max_loss_usd), 75.0)
        self.assertIn("implied move", opens[0]["reason"])

    def test_stands_aside_when_the_options_are_not_rich(self):
        out = self.run_seed(self.market(f"{FRI} 10:30", iv=0.08, rv=0.10))
        self.assertEqual(self.opens(out), [])
        self.assertIn("under", out["thought"])

    def test_never_opens_outside_its_window_or_past_the_expiry_day_cut(self):
        for now, params in ((f"{FRI} 09:45", {}), (f"{FRI} 14:10", {}), (f"{FRI} 14:40", {"entry_end": 930})):
            with self.subTest(now=now):
                ctx = self.market(now)
                ctx["params"] = params
                self.assertEqual(self.opens(self.run_seed(ctx)), [])

    def opened(self):
        ctx = self.market(f"{FRI} 10:30")
        intent = self.opens(self.run_seed(ctx))[0]
        return intent, structures.parse("alpaca-paper", intent)

    def test_takes_its_profit_target(self):
        intent, order = self.opened()
        now = f"{FRI} 12:30"
        ctx = self.market(now, iv=0.12)  # the premium has decayed: buying it back is cheap
        ctx["positions"] = [held(intent, float(order.held_limit))]
        out = self.run_seed(ctx)
        closes = self.closes(out)
        self.assertEqual(len(closes), 1, out["thought"])
        self.assertEqual({l["occ"] for l in closes[0]["legs"]}, {l["occ"] for l in intent["legs"]})
        self.assertIn("profit target", closes[0]["reason"])
        self.assertEqual(self.opens(out), [], "SPY is held: no second condor on it")

    def test_stops_when_the_buy_back_is_twice_the_credit(self):
        intent, order = self.opened()
        short_call = min(float(l["occ"][-8:]) / 1000 for l in intent["legs"] if l["role"] == "short" and "C" in l["occ"][-9])
        now = f"{FRI} 11:30"
        ctx = self.market(now, spot=short_call + 0.5)
        ctx["positions"] = [held(intent, float(order.held_limit))]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("stop", closes[0]["reason"])

    def test_leaves_before_the_close_of_its_expiry_day(self):
        intent, order = self.opened()
        ctx = self.market(f"{FRI} 15:26")
        ctx["chain"] = []  # the legs out of the chain: the House's mark (here, what was paid) is the price
        ctx["positions"] = [held(intent, float(order.held_limit))]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("time exit", closes[0]["reason"])
        self.assertIn("the House's mark", closes[0]["reason"])
        order = structures.parse("alpaca-paper", closes[0])
        self.assertEqual(order.action, "close")
        ctx["now"] = utc(f"{FRI} 15:10")
        self.assertEqual(self.closes(self.run_seed(ctx)), [], "before its exit minute it holds")

    def test_an_entry_that_never_filled_does_not_spend_the_day(self):
        # Sept 25, 2026: entries were counted when sent, and on the structure replay one unfilled
        # order used a founder's whole day. Only a fill (or a working order) counts now.
        ctx = self.market(f"{FRI} 10:30")
        ctx["params"] = {"max_entries_day": 1}
        first = self.run_seed(ctx)
        self.assertEqual(len(self.opens(first)), 1)
        again = self.market(f"{FRI} 11:00")
        again["params"], again["memory"] = {"max_entries_day": 1}, first["memory"]
        self.assertEqual(len(self.opens(self.run_seed(again))), 1, "the first order died unfilled: the day is not spent")
        intent = self.opens(first)[0]
        filled = self.market(f"{FRI} 11:00")
        filled["params"], filled["memory"] = {"max_entries_day": 1}, first["memory"]
        filled["positions"] = [held(intent, float(structures.parse("alpaca-paper", intent).held_limit), opened_ny=f"{FRI} 10:45")]
        filled["positions"][0]["legs"] = intent["legs"]
        out = self.run_seed(filled)
        self.assertEqual(self.opens(out), [])
        filled["positions"] = []
        filled["memory"] = out["memory"]
        filled["now"] = utc(f"{FRI} 12:00")
        self.assertEqual(self.opens(self.run_seed(filled)), [], "a condor that filled and closed still counts")

    def test_holds_between_its_exits_and_cancels_stale_orders(self):
        intent, order = self.opened()
        ctx = self.market(f"{FRI} 10:45")
        ctx["positions"] = [held(intent, float(order.held_limit))]
        ctx["open_orders"] = [{"order_id": "ord-9", "structure": "iron_condor", "legs": intent["legs"], "side": "buy", "action": "open",
                               "quantity": 1, "limit_price": 0.2, "submitted_at": utc(f"{FRI} 10:20")}]
        out = self.run_seed(ctx)
        self.assertEqual(self.closes(out), [], out["thought"])
        self.assertEqual(out["cancels"], ["ord-9"])


# ------------------------------------------------------------------------------ the put spread on a dip
class PutSpreadDip(FounderCase):
    SEED = "options-putspread-dip"

    def market(self, now, *, dip=0.6, trend=0.0004, iv=0.22, spot=760.0):
        high = spot / (1 - dip / 100.0)
        opened = datetime.strptime(now, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
        count = int((opened - opened.replace(hour=9, minute=30)).total_seconds() // 3600)
        path = [high] * max(0, count - 1) + [spot]
        rows = chain("SPY", spot, now, [FRI, MON, "2026-09-30"], vol=iv)
        return ctx_for(now, rows, {"SPY": bars(spot, now, sessions=14, minutes=60, annual_vol=0.10, trend=trend, today_path=path),
                                   "QQQ": [], "IWM": []})

    def test_sells_a_put_vertical_after_a_dip_in_an_uptrend(self):
        out = self.run_seed(self.market("2026-09-24 12:40"))
        opens = self.opens(out)
        self.assertEqual(len(opens), 1, out["thought"])
        order = structures.parse("alpaca-paper", opens[0])
        self.assertEqual(order.spec.type, "credit_vertical")
        self.assertEqual({leg.right for leg in order.spec.legs}, {"put"})
        self.assertLessEqual(float(order.max_loss_usd), 75.0)

    def test_no_dip_or_no_uptrend_no_trade(self):
        for kwargs in ({"dip": 0.05}, {"trend": -0.0004}):
            with self.subTest(**kwargs):
                self.assertEqual(self.opens(self.run_seed(self.market("2026-09-24 12:40", **kwargs))), [])

    def test_exits_by_the_next_session_and_on_its_stop(self):
        intent = self.opens(self.run_seed(self.market("2026-09-24 12:40")))[0]
        order = structures.parse("alpaca-paper", intent)
        position = held(intent, float(order.held_limit), opened_ny="2026-09-24 12:45")
        ctx = self.market("2026-09-24 13:40", dip=0.6)
        ctx["positions"] = [position]
        self.assertEqual(self.closes(self.run_seed(ctx)), [], "the same session, no exit yet")
        if order.spec.expiry > FRI:
            ctx = self.market(f"{FRI} 15:31", dip=0.1)
            ctx["positions"] = [position]
            self.assertEqual(len(self.closes(self.run_seed(ctx))), 1, "the session after: out at its exit minute")
        short = max(float(leg.strike) for leg in order.spec.legs)
        ctx = self.market("2026-09-24 14:40", spot=short - 0.8, dip=0.9)
        ctx["positions"] = [position]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("stop", closes[0]["reason"])


# ------------------------------------------------------------------------------ the quiet iron butterfly
class IronflyQuiet(FounderCase):
    SEED = "options-ironfly-quiet"

    def market(self, now, *, noisy=False, iv=0.50, spot=760.0):
        opened = datetime.strptime(now, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
        count = int((opened - opened.replace(hour=9, minute=30)).total_seconds() // 900)
        path = [spot * (1 + (0.004 if (noisy and j % 2) else 0.0) - 0.00005 * (j % 2)) for j in range(count - 1)] + [spot]
        return ctx_for(now, chain("SPY", spot, now, [FRI, MON], vol=iv), {"SPY": bars(spot, now, annual_vol=0.04, today_path=path),
                                                                          "QQQ": [], "IWM": []})

    def test_sells_an_at_the_money_iron_butterfly_in_a_quiet_midday(self):
        out = self.run_seed(self.market(f"{FRI} 12:00"))
        opens = self.opens(out)
        self.assertEqual(len(opens), 1, out["thought"])
        order = structures.parse("alpaca-paper", opens[0])
        self.assertEqual(order.spec.type, "iron_butterfly")
        body = {float(leg.strike) for leg in order.spec.legs if leg.sign < 0}
        self.assertEqual(body, {760.0})

    def test_a_noisy_midday_or_the_morning_is_left_alone(self):
        self.assertEqual(self.opens(self.run_seed(self.market(f"{FRI} 12:00", noisy=True))), [])
        self.assertEqual(self.opens(self.run_seed(self.market(f"{FRI} 10:30"))), [])

    def test_flat_by_its_flat_time_and_on_its_target(self):
        intent = self.opens(self.run_seed(self.market(f"{FRI} 12:00")))[0]
        order = structures.parse("alpaca-paper", intent)
        position = held(intent, float(order.held_limit), opened_ny=f"{FRI} 12:05")
        ctx = self.market(f"{FRI} 15:16")
        ctx["positions"] = [position]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("time exit", closes[0]["reason"])
        ctx = self.market(f"{FRI} 14:30", iv=0.03)
        ctx["positions"] = [position]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("profit target", closes[0]["reason"])


# ------------------------------------------------------------------------------ the cheap strangle
class StrangleCheap(FounderCase):
    SEED = "options-strangle-cheap"
    WED, NEXT = "2026-09-23", "2026-09-25"

    def market(self, now, *, iv=0.10, rv=0.45, spot=220.0):
        rows = chain("IWM", spot, now, [self.WED, self.NEXT], vol=iv)
        return ctx_for(now, rows, {"IWM": bars(spot, now, sessions=12, minutes=60, annual_vol=rv), "QQQ": [], "SPY": []})

    def test_buys_a_strangle_when_implied_is_cheap_against_realized(self):
        out = self.run_seed(self.market("2026-09-21 10:30"))
        opens = self.opens(out)
        self.assertEqual(len(opens), 1, out["thought"])
        order = structures.parse("alpaca-paper", opens[0])
        self.assertIn(order.spec.type, ("long_strangle", "long_straddle"))
        self.assertFalse(order.spec.credit)
        self.assertLessEqual(float(order.max_loss_usd), 75.0)

    def test_rich_options_are_not_bought(self):
        self.assertEqual(self.opens(self.run_seed(self.market("2026-09-21 10:30", iv=0.40, rv=0.10))), [])

    def test_takes_a_move_and_leaves_after_a_session(self):
        intent = self.opens(self.run_seed(self.market("2026-09-21 10:30")))[0]
        order = structures.parse("alpaca-paper", intent)
        position = held(intent, float(order.held_limit), opened_ny="2026-09-21 10:40")
        ctx = self.market("2026-09-21 13:00", spot=214.0)
        ctx["positions"] = [position]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("profit target", closes[0]["reason"])
        ctx = self.market("2026-09-22 15:31")
        ctx["chain"] = []
        ctx["positions"] = [position]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("time exit", closes[0]["reason"])


# ------------------------------------------------------------------------------ the term calendar
class CalendarTerm(FounderCase):
    SEED = "options-calendar-term"
    NEAR, FAR = "2026-09-23", "2026-09-30"

    def market(self, now, *, front=0.70, back=0.40, spot=12.0):
        rows = chain("F", spot, now, [self.NEAR, self.FAR], vols={self.NEAR: front, self.FAR: back}, step=0.5, span=3)
        return ctx_for(now, rows, {"F": bars(spot, now, sessions=12, minutes=60, annual_vol=0.35), "IWM": [], "SOFI": [], "INTC": [],
                                   "PFE": [], "T": []})

    def test_buys_a_calendar_into_a_front_kink(self):
        out = self.run_seed(self.market("2026-09-21 11:00"))
        opens = self.opens(out)
        self.assertEqual(len(opens), 1, out["thought"])
        order = structures.parse("alpaca-paper", opens[0])
        self.assertEqual(order.spec.type, "calendar")
        short = [leg for leg in order.spec.legs if leg.sign < 0][0]
        self.assertEqual(short.expiry, self.NEAR)
        self.assertEqual(order.spec.expiry, self.NEAR)

    def test_a_flat_term_structure_is_left_alone(self):
        self.assertEqual(self.opens(self.run_seed(self.market("2026-09-21 11:00", front=0.40))), [])

    def test_closes_before_the_near_expiry(self):
        intent = self.opens(self.run_seed(self.market("2026-09-21 11:00")))[0]
        order = structures.parse("alpaca-paper", intent)
        position = held(intent, float(order.held_limit), opened_ny="2026-09-21 11:05")
        ctx = self.market(f"{self.NEAR} 15:20")
        ctx["chain"] = []
        ctx["positions"] = [position]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("time exit", closes[0]["reason"])


# ------------------------------------------------------------------------------ the pin butterfly
class ButterflyPin(FounderCase):
    SEED = "options-butterfly-pin"

    def market(self, now, *, busy=760.0, heavy=5000, iv=0.30, spot=760.2, memory=None):
        volume = {(s, r): (heavy if s == busy else 100) for s in (757.0, 758.0, 759.0, 760.0, 761.0, 762.0, 763.0) for r in ("call", "put")}
        ctx = ctx_for(now, chain("SPY", spot, now, [FRI, MON], vol=iv, volume=volume), {"SPY": bars(spot, now, annual_vol=0.06),
                                                                                        "QQQ": [], "IWM": []})
        ctx["memory"] = dict(memory or {})
        return ctx

    def test_notes_the_volumes_then_buys_the_butterfly_at_the_busiest_strike(self):
        first = self.run_seed(self.market(f"{FRI} 11:50", heavy=100))
        self.assertIn("snap", first["memory"])
        out = self.run_seed(self.market(f"{FRI} 13:50", memory=first["memory"]))
        opens = self.opens(out)
        self.assertEqual(len(opens), 1, out["thought"])
        order = structures.parse("alpaca-paper", opens[0])
        self.assertEqual(order.spec.type, "long_butterfly")
        body = [leg for leg in order.spec.legs if leg.sign < 0][0]
        self.assertEqual((float(body.strike), body.ratio), (760.0, 2))
        self.assertEqual(order.spec.expiry, FRI)

    def test_no_pin_no_trade_and_nothing_after_the_cut(self):
        first = self.run_seed(self.market(f"{FRI} 11:50", heavy=100))
        flat = self.run_seed(self.market(f"{FRI} 13:50", heavy=100, memory=first["memory"]))
        self.assertEqual(self.opens(flat), [])
        late = self.market(f"{FRI} 14:31", memory=first["memory"])
        late["params"] = {"entry_end": 865}
        self.assertEqual(self.opens(self.run_seed(late)), [])

    def test_sells_before_the_close(self):
        first = self.run_seed(self.market(f"{FRI} 11:50", heavy=100))
        intent = self.opens(self.run_seed(self.market(f"{FRI} 13:50", memory=first["memory"])))[0]
        order = structures.parse("alpaca-paper", intent)
        ctx = self.market(f"{FRI} 15:26", memory=first["memory"])
        ctx["positions"] = [held(intent, float(order.held_limit), opened_ny=f"{FRI} 13:55")]
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("the ", closes[0]["reason"])
        ctx["chain"] = []
        closes = self.closes(self.run_seed(ctx))
        self.assertEqual(len(closes), 1)
        self.assertIn("time exit", closes[0]["reason"])


if __name__ == "__main__":
    unittest.main()
