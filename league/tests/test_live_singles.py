"""Long calls and long puts as real types (the sprint, B4, Sept 26, 2026): one list everywhere (the constitution, league.ci
and the gateway), single-leg `buy_to_open` and `sell_to_close` limit orders the gateway admits, maximum loss = premium
plus fees, and the expiry-day rule (closed before the close cutoff whatever the moneyness while it has a bid: the account
cannot carry the 100 shares an exercise brings). Against the venue's recorded shapes (`live_fakes`: a simple order's
`legs` is null) with invented numbers."""

import datetime as dt
import re
import unittest
from decimal import Decimal as D
from pathlib import Path

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.live.real import (ROrder, RLeg, SINGLE_TYPES, is_single, mleg_body, order_body, single_body,
                                  single_leg_body)
    from league.live.venue import occ_symbol
    from league.tests.live_fakes import MONDAY, VERTICAL, at, family

REPO = Path(__file__).resolve().parents[2]

LONG = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"hold": 3, "opens": 1, "dte": 1, "right": "C", "strike": 603.0, "after": 0, "limit": "natural"}
STATE = {"opened": 0}

def decide(ctx):
    out = []
    for p in ctx.positions:
        if p["held_minutes"] >= ctx.params["hold"]:
            out.append({"close": p["id"], "limit": "natural", "note": "held long enough"})
    if ctx.minute < ctx.params["after"]:
        return out
    if not ctx.positions and not ctx.orders and STATE["opened"] < ctx.params["opens"]:
        STATE["opened"] += 1
        kind = "long_call" if ctx.params["right"] == "C" else "long_put"
        out.append({"open": kind, "root": "SPY", "qty": 1, "limit": ctx.params["limit"], "tag": "single",
                    "legs": [{"side": "long", "right": ctx.params["right"], "dte": ctx.params["dte"],
                              "strike": ctx.params["strike"]}]})
    return out
'''


def gateway_fields() -> set[str]:
    """`ALPACA_ORDER_FIELDS` as `gateway/lib/caps.mjs` spells it: what a single-leg order may carry."""
    text = (REPO / "gateway" / "lib" / "caps.mjs").read_text(encoding="utf-8")
    body = re.search(r"ALPACA_ORDER_FIELDS = new Set\(\[(.*?)\]\)", text, re.S).group(1)
    return set(re.findall(r"'([a-z_]+)'", body))


class OneList(unittest.TestCase):
    def test_the_constitution_league_ci_the_live_book_and_the_gateway_name_the_same_singles(self):
        from league import ci
        from league.constitution import CONSTITUTION, OPTIONS_REAL_TYPES, OPTIONS_SINGLE_TYPES

        self.assertEqual(OPTIONS_SINGLE_TYPES, ("long_call", "long_put"))
        self.assertEqual(ci.GATEWAY_SINGLE_TYPES, OPTIONS_SINGLE_TYPES)
        self.assertTrue(set(OPTIONS_SINGLE_TYPES) <= set(OPTIONS_REAL_TYPES))
        caps = (REPO / "gateway" / "lib" / "caps.mjs").read_text(encoding="utf-8")
        self.assertIn("export const SINGLE_LEG_TYPES = ['long_call', 'long_put'];", caps)
        real = CONSTITUTION["options_money"]["real_types"]
        self.assertEqual(real, ["debit_vertical", "long_butterfly", "long_call", "long_put", "credit_vertical", "iron_condor",
                                "iron_butterfly"])                         # money rules v3 (D3)
        self.assertEqual(ci.gateway_structures(), (sorted(real), []), "the deployed gateway opens exactly these")
        self.assertEqual(ci.check_structures(), [])
        if HAVE:
            self.assertEqual(SINGLE_TYPES, OPTIONS_SINGLE_TYPES)


@unittest.skipUnless(HAVE, "numpy not installed")
class Bodies(unittest.TestCase):
    def order(self, action, *, type_="long_call", limit="1.23"):
        leg = RLeg("SPY261016C00603000", 1, 1, True, 603.0, "2026-10-16", 7)
        return ROrder(4, "lv-ab12-0000004-call", "call@1:r", "call", action, type_, "SPY", [leg], 2, 1.23, limit, None,
                      0.0, "2026-09-28", 3)

    def test_a_single_opens_with_buy_to_open_and_closes_with_sell_to_close_at_a_positive_premium(self):
        opened, closed = order_body(self.order("open")), order_body(self.order("close"))
        self.assertEqual(opened, {"symbol": "SPY261016C00603000", "qty": "2", "side": "buy", "type": "limit",
                                  "limit_price": "1.23", "time_in_force": "day", "position_intent": "buy_to_open",
                                  "client_order_id": "lv-ab12-0000004-call"})
        self.assertEqual((closed["side"], closed["position_intent"], closed["limit_price"]), ("sell", "sell_to_close", "1.23"))
        for body in (opened, closed):
            self.assertTrue(set(body) <= gateway_fields(), set(body) - gateway_fields())
            self.assertNotIn("legs", body)
            self.assertNotIn("order_class", body)
        self.assertTrue(is_single(self.order("open")))
        self.assertFalse(is_single(self.order("open", type_="debit_vertical")))
        self.assertEqual(single_body(self.order("close")), closed)
        self.assertEqual(order_body(self.order("close_leg")), single_leg_body(self.order("close_leg")))
        vertical = self.order("open", type_="debit_vertical")
        vertical.legs = vertical.legs + [RLeg("SPY261016C00604000", -1, 1, True, 604.0, "2026-10-16", 8)]
        self.assertEqual(order_body(vertical), mleg_body(vertical))


@unittest.skipUnless(HAVE, "numpy not installed")
class RealSingles(LiveCase):
    def refusals(self):
        return [p["why"] for p, a in self.ledger.of("live.refusal")]

    def test_a_long_call_opens_and_closes_with_single_leg_limit_orders_and_loses_at_most_its_premium(self):
        live = self.make([family("call", LONG, band="probe", structure="long_call", typical=60.0)])
        self.run_to(9, 31)
        [opened] = self.venue.sent
        symbol = occ_symbol("SPY", (MONDAY + dt.timedelta(days=1)).isoformat(), True, 603.0)
        _, ask = self.market.quote(symbol)
        self.assertEqual((opened["symbol"], opened["side"], opened["position_intent"], opened["type"], opened["time_in_force"]),
                         (symbol, "buy", "buy_to_open", "limit", "day"))
        self.assertEqual(D(opened["limit_price"]), D(str(ask)), "the program's natural: the ask, on the contract's tick")
        self.assertTrue(set(opened) <= gateway_fields())
        [pos] = live.book.positions.values()
        self.assertEqual((pos.type, pos.collateral, len(pos.legs)), ("long_call", 0.0, 1))
        self.assertAlmostEqual(pos.max_loss_share, pos.entry)
        self.assertAlmostEqual(pos.max_loss, pos.entry * 100 * pos.qty)
        # Sized by maximum loss (5% of 5,481.65 = 274.08, premium and fees a contract), not by the program's qty of 1.
        unit = D(str(round(pos.entry * 100 + 2 * pos.fees / pos.qty, 2)))
        self.assertEqual(pos.qty, int(D("274.0825") // unit))
        [(fill, agent)] = self.ledger.of("book.fill")
        self.assertEqual((agent, fill["instrument"]["right"], fill["instrument"]["symbol"]), ("call", "call", "SPY"))
        from league.publish import trade_of

        self.assertEqual(trade_of(fill, close=False)["structure"], "long_call")
        self.run_to(9, 36)
        closes = [b for b in self.venue.sent if b.get("position_intent") == "sell_to_close"]
        self.assertEqual(len(closes), 1)
        self.assertEqual((closes[0]["side"], closes[0]["symbol"], closes[0]["type"]), ("sell", symbol, "limit"))
        self.assertGreater(D(closes[0]["limit_price"]), 0)
        self.assertEqual(live.book.positions, {})
        [trade] = live.book.closed_trades()
        self.assertEqual(trade["max_loss"], round(pos.entry * 100 * pos.opened_qty, 2), "its premium: all it can lose")
        self.assertAlmostEqual(trade["pnl"], round((pos.exit_value_qty - pos.entry * pos.opened_qty) * 100 - pos.fees, 2),
                               places=2)
        self.assertIn("real", {r["source"] for r in self.families.forward_rows("call")})
        self.assertEqual(live.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False), [])

    def test_a_long_put_too(self):
        live = self.make([family("put", LONG, band="probe", structure="long_put",
                                 params={"hold": 2, "opens": 1, "dte": 1, "right": "P", "strike": 597.0, "after": 0,
                                         "limit": "natural"})])
        self.run_to(9, 31)
        [opened] = self.venue.sent
        self.assertEqual((opened["symbol"][-9], opened["position_intent"]), ("P", "buy_to_open"))
        self.run_to(9, 35)
        self.assertEqual([b["position_intent"] for b in self.venue.sent], ["buy_to_open", "sell_to_close"])
        self.assertEqual(live.book.positions, {})

    def test_a_mid_limit_rests_for_its_time_in_force_at_the_gyms_price(self):
        # A patient rule, as the Gym prices it: the mid on the contract's tick, rounded passively; never the natural.
        live = self.make([family("call", LONG.replace('"limit": ctx.params["limit"],', '"limit": "mid", "tif": 2,'),
                                 band="probe", structure="long_call", params={"hold": 600, "opens": 1, "dte": 1, "right": "C",
                                                                               "strike": 603.0, "after": 0})])
        self.venue.fill = "none"
        self.run_to(9, 31)
        [opened] = self.venue.sent
        symbol = opened["symbol"]
        bid, ask = self.market.quote(symbol)
        from league.gym import venue as V

        expect = V.round_price(0.5 * (bid + ask), V.leg_tick("SPY", 0.5 * (bid + ask)), up=False)
        self.assertAlmostEqual(float(opened["limit_price"]), expect)
        self.assertLess(float(opened["limit_price"]), ask)
        self.run_to(9, 33)
        self.assertEqual(self.venue.cancels, [], "tif 2: the quotes of 9:32 through 9:34")
        self.run_to(9, 34)
        self.assertEqual(len(self.venue.cancels), 1)

    def test_a_single_never_takes_the_other_side_of_a_contract_the_account_holds(self):
        # The vertical holds 600C long and 601C short; a long 601C would net against the short leg (the wash-trade rule).
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600}),
                          family("call", LONG, band="probe", structure="long_call",
                                 params={"hold": 600, "opens": 1, "dte": 1, "right": "C", "strike": 601.0, "after": 573,
                                         "limit": "natural"})])
        self.run_to(9, 36)
        self.assertEqual(len(self.venue.sent), 1)
        self.assertTrue(any("positions net across the account" in w for w in self.refusals()), self.refusals())


@unittest.skipUnless(HAVE, "numpy not installed")
class ExpiryDay(LiveCase):
    """SPY: the House's close cutoff is 15:25 ET (the venue's 15:30), and its expiring closes start 10 minutes before."""

    def expiring(self, strike, quote, right="C"):
        symbol = occ_symbol("SPY", MONDAY.isoformat(), right == "C", float(strike))
        self.market.overrides[symbol] = quote
        return symbol

    def test_an_expiring_long_call_out_of_the_money_with_a_bid_is_sold_before_the_cutoff(self):
        self.clock.set(at(MONDAY, 14, 40))
        symbol = self.expiring(610, (0.03, 0.05, 20, 20))               # 1.7% out of the money: not "near" it
        live = self.make([family("call", LONG, band="probe", structure="long_call",
                                 params={"hold": 600, "opens": 1, "dte": 0, "right": "C", "strike": 610.0, "after": 0,
                                         "limit": "natural"})])
        self.run_to(14, 41)
        self.assertEqual([b["symbol"] for b in self.venue.sent], [symbol])
        self.run_to(15, 14)
        self.assertEqual(len(self.venue.sent), 1, "held to the window")
        self.run_to(15, 15)
        [close] = [b for b in self.venue.sent if b.get("position_intent") == "sell_to_close"]
        self.assertEqual((close["symbol"], close["side"], close["limit_price"]), (symbol, "sell", "0.03"))
        self.assertEqual(live.book.positions, {}, "sold at 15:15, before the 15:25 cutoff: it can never exercise")

    def test_an_expiring_long_put_in_the_money_is_sold_and_a_programs_own_close_meets_the_houses(self):
        self.clock.set(at(MONDAY, 14, 40))
        self.expiring(601, (1.40, 1.50, 20, 20), right="P")
        live = self.make([family("put", LONG, band="probe", structure="long_put",
                                 params={"hold": 600, "opens": 1, "dte": 0, "right": "P", "strike": 601.0, "after": 0,
                                         "limit": "natural"})])
        self.run_to(14, 41)
        self.assertEqual(len(live.book.positions), 1)
        self.venue.fill = "none"                                          # the first sale rests: re-priced each minute
        self.run_to(15, 17)
        sales = [b for b in self.venue.sent if b.get("position_intent") == "sell_to_close"]
        self.assertGreaterEqual(len(sales), 2)
        self.assertEqual([b["limit_price"] for b in sales[:2]], ["1.40", "1.39"], "the natural, then a cent's concession")
        self.venue.fill = "natural"
        self.run_to(15, 19)
        self.assertEqual(live.book.positions, {})

    def test_the_last_forced_close_before_the_cutoff_is_left_working(self):
        # The review of #390 (lens 2): re-priced each minute, but the last one before the cutoff is never cancelled, for
        # nothing could replace it after it.
        self.clock.set(at(MONDAY, 14, 40))
        self.expiring(601, (1.40, 1.50, 20, 20), right="P")
        live = self.make([family("put", LONG, band="probe", structure="long_put",
                                 params={"hold": 600, "opens": 1, "dte": 0, "right": "P", "strike": 601.0, "after": 0,
                                         "limit": "natural"})])
        self.run_to(14, 41)
        self.venue.fill = "none"
        self.run_to(15, 30)
        [working] = [o for o in live.book.orders.values() if o.action == "close"]
        self.assertTrue(working.forced)
        self.assertEqual(working.placed_minute, 15 * 60 + 23 - 570, "sent at 15:23 and never cancelled at 15:24")
        self.assertEqual(working.status, "working")

    def test_an_expiring_long_call_with_no_bid_far_out_of_the_money_is_left_to_expire(self):
        self.clock.set(at(MONDAY, 14, 40))
        self.expiring(615, (0.0, 0.01, 0, 50))                           # nothing would buy it; it cannot exercise
        live = self.make([family("call", LONG, band="probe", structure="long_call",
                                 params={"hold": 600, "opens": 1, "dte": 0, "right": "C", "strike": 615.0, "after": 0,
                                         "limit": "natural"})])
        self.run_to(15, 24)
        self.assertEqual([b["position_intent"] for b in self.venue.sent], ["buy_to_open"])
        [pos] = live.book.positions.values()
        self.assertEqual(live._expiry_close(pos, live.day, 15 * 60 + 20 - 570, 15 * 60 + 20), "")


if __name__ == "__main__":
    unittest.main()
