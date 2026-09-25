"""Level-3 debit verticals: what one is, what it can lose, and the one position a book holds for it.

Written Sept 23, 2026 (the learn-and-unblock run, workstream O) against the design in
docs/design/2026-09-24-level-3-debit-verticals.md; the spread held as ONE instrument priced at its
net was added Sept 25, 2026 (the options-desk run). No venue has seen a multi-leg order from this
code base: these tests pin what can be known without one.
"""

import re
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.adapters.alpaca import alpaca_symbol
from ltcm.broker import Fill

from league import verticals
from league.verticals import DebitVertical, cap_refusal, count_trades, fits_caps, max_gain, max_loss, mleg_body, parse_vertical
from league.venues import instrument_for

D = Decimal
VENUE = "alpaca-paper"
C13, C14, C15 = "F261016C00013000", "F261016C00014000", "F261016C00015000"
P13, P14 = "F261016P00013000", "F261016P00014000"
C13_LATER = "F261023C00013000"
SOFI13 = "SOFI261016C00013000"


def spec(long=C13, short=C14, **overrides):
    """A bull call spread on F, one for $0.35 a share: the schema the design gives strategies."""
    row = {"spread": "debit_vertical", "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.35,
           "reason": "test", "legs": [{"occ": long, "role": "long"}, {"occ": short, "role": "short"}]}
    row.update(overrides)
    return row


def leg(occ, side, quantity="1", at="2026-10-01T14:00:00.000Z", price="0.50", order_id="o1"):
    """One per-leg fill as the adapter's `fills()` would report it (assumed shape, unverified)."""
    return Fill(id=f"{at}::{occ}::{side}", order_id=order_id, desk_id="", instrument=instrument_for(VENUE, {"occ": occ}),
                side=side, quantity=D(quantity), price=D(price), fee=D(0), at=at)


class Parsing(unittest.TestCase):
    def test_a_bull_call_spread_parses(self):
        v = parse_vertical(VENUE, spec())
        self.assertIsInstance(v, DebitVertical)
        self.assertEqual((v.underlying, v.expiry, v.right, v.venue), ("F", "2026-10-16", "call", VENUE))
        self.assertEqual((v.long.strike, v.short.strike, v.width), (D(13), D(14), D(1)))
        self.assertEqual((v.quantity, v.net_debit, v.side, v.reason), (D(1), D("0.35"), "buy", "test"))
        self.assertEqual(v.multiplier, D(100))
        self.assertEqual(v.key, "spread:F:alpaca-paper:2026-10-16:call:13/14")

    def test_a_bear_put_spread_parses_with_the_higher_strike_long(self):
        v = parse_vertical(VENUE, spec(long=P14, short=P13))
        self.assertEqual((v.right, v.long.strike, v.short.strike, v.width), ("put", D(14), D(13), D(1)))

    def test_legs_may_be_spelled_out_instead_of_an_occ_code(self):
        long = {"symbol": "F", "expiry": "2026-10-16", "strike": "13", "right": "call", "role": "long"}
        short = {"symbol": "F", "expiry": "2026-10-16", "strike": "14", "right": "call", "role": "short"}
        v = parse_vertical(VENUE, spec(legs=[long, short]))
        self.assertEqual(v.key, parse_vertical(VENUE, spec()).key)
        self.assertEqual([alpaca_symbol(v.long), alpaca_symbol(v.short)], [C13, C14])

    def test_a_close_is_the_same_spread_sold(self):
        v = parse_vertical(VENUE, spec(side="sell", limit_price=0.60))
        self.assertEqual((v.side, v.net_debit), ("sell", D("0.60")))
        self.assertEqual(v.key, parse_vertical(VENUE, spec()).key)

    def test_a_credit_spread_is_refused(self):
        """The same two calls with the short leg at the lower strike is a written call with a hedge."""
        with self.assertRaisesRegex(ValueError, "credit spread"):
            parse_vertical(VENUE, spec(long=C14, short=C13))
        with self.assertRaisesRegex(ValueError, "credit spread"):
            parse_vertical(VENUE, spec(long=P13, short=P14))

    def test_mixed_rights_expiries_or_underlyings_are_refused(self):
        for long, short in ((C13, P14), (C13, C13_LATER), (SOFI13, C14)):
            with self.assertRaisesRegex(ValueError, "one underlying, expiry and right"):
                parse_vertical(VENUE, spec(long=long, short=short))

    def test_one_strike_twice_is_not_a_vertical(self):
        with self.assertRaisesRegex(ValueError, "two strikes"):
            parse_vertical(VENUE, spec(long=C13, short=C13))

    def test_exactly_two_legs_one_long_and_one_short(self):
        three = spec()["legs"] + [{"occ": C15, "role": "short"}]
        with self.assertRaisesRegex(ValueError, "two legs"):
            parse_vertical(VENUE, spec(legs=three))
        with self.assertRaisesRegex(ValueError, "two legs"):
            parse_vertical(VENUE, spec(legs=spec()["legs"][:1]))
        with self.assertRaisesRegex(ValueError, "one long and one short"):
            parse_vertical(VENUE, spec(legs=[{"occ": C13, "role": "long"}, {"occ": C14, "role": "long"}]))
        with self.assertRaisesRegex(ValueError, "one long and one short"):
            parse_vertical(VENUE, spec(legs=[{"occ": C13, "side": "buy"}, {"occ": C14, "side": "sell"}]))

    def test_a_stock_or_a_kalshi_market_is_not_a_leg(self):
        with self.assertRaisesRegex(ValueError, "option contracts"):
            parse_vertical(VENUE, spec(legs=[{"symbol": "F", "role": "long"}, {"occ": C14, "role": "short"}]))
        with self.assertRaisesRegex(ValueError, "option contracts"):
            parse_vertical("kalshi", spec(legs=[{"market": "KXBTCD-X", "leg": "yes", "role": "long"}, {"market": "KXBTCD-Y", "leg": "yes", "role": "short"}]))

    def test_only_a_debit_vertical_limit_order_is_admitted(self):
        with self.assertRaisesRegex(ValueError, "debit_vertical"):
            parse_vertical(VENUE, spec(spread="iron_condor"))
        with self.assertRaisesRegex(ValueError, "debit_vertical"):
            parse_vertical(VENUE, {k: v for k, v in spec().items() if k != "spread"})
        with self.assertRaisesRegex(ValueError, "limit order"):
            parse_vertical(VENUE, spec(type="market"))
        with self.assertRaisesRegex(ValueError, "limit order"):
            parse_vertical(VENUE, spec(limit_price=None))

    def test_the_net_debit_is_positive_whole_cents_and_under_the_width(self):
        for bad in (0, -0.35, 0.355, "abc"):
            with self.assertRaisesRegex(ValueError, "net (debit|price)"):
                parse_vertical(VENUE, spec(limit_price=bad))
        with self.assertRaisesRegex(ValueError, "can never pay"):
            parse_vertical(VENUE, spec(limit_price=1.00))  # a $1 debit on a $1-wide spread
        with self.assertRaisesRegex(ValueError, "can never pay"):
            parse_vertical(VENUE, spec(limit_price=1.05))
        # A close names the least it will take, which the width does not bound the same way.
        parse_vertical(VENUE, spec(side="sell", limit_price=0.99))

    def test_quantity_is_whole_spreads(self):
        for bad in (0, -1, 0.5, "1.5"):
            with self.assertRaisesRegex(ValueError, "whole number of spreads"):
                parse_vertical(VENUE, spec(quantity=bad))
        self.assertEqual(parse_vertical(VENUE, spec(quantity="3")).quantity, D(3))

    def test_side_and_reason_are_required(self):
        with self.assertRaisesRegex(ValueError, "buy .* or sell"):
            parse_vertical(VENUE, spec(side="short"))
        with self.assertRaisesRegex(ValueError, "reason"):
            parse_vertical(VENUE, spec(reason=""))

    def test_the_dataclass_holds_the_same_invariants_when_built_directly(self):
        long, short = instrument_for(VENUE, {"occ": C14}), instrument_for(VENUE, {"occ": C13})
        with self.assertRaisesRegex(ValueError, "credit spread"):
            DebitVertical(long=long, short=short, quantity=D(1), net_debit=D("0.35"))
        with self.assertRaisesRegex(ValueError, "whole number of spreads"):
            DebitVertical(long=short, short=long, quantity=D("0.5"), net_debit=D("0.35"))


class Arithmetic(unittest.TestCase):
    def test_maximum_loss_is_the_net_debit_a_hundredfold_per_spread(self):
        v = parse_vertical(VENUE, spec(quantity=2))
        self.assertEqual(max_loss(v), D("70.00"))  # 0.35 x 100 x 2
        self.assertEqual(max_gain(v), D("130.00"))  # (1.00 - 0.35) x 100 x 2

    def test_a_close_can_lose_nothing_more(self):
        v = parse_vertical(VENUE, spec(side="sell", limit_price=0.60))
        self.assertEqual((max_loss(v), max_gain(v)), (D(0), D(0)))

    def test_the_order_cap_bounds_one_opening_orders_maximum_loss(self):
        self.assertTrue(fits_caps(parse_vertical(VENUE, spec(quantity=2)), D(75), D(100)))  # $70 under $75
        three = parse_vertical(VENUE, spec(quantity=3))  # $105
        self.assertFalse(fits_caps(three, D(75), D(200)))
        self.assertEqual(cap_refusal(three, D(75), D(200)), "a spread that can lose $105.00 is over the $75 order cap")

    def test_the_position_cap_bounds_the_spreads_held_plus_this_one(self):
        v = parse_vertical(VENUE, spec(quantity=2))  # $70
        self.assertIsNone(cap_refusal(v, D(75), D(100)))
        self.assertEqual(cap_refusal(v, D(75), D(100), held_max_loss=D(35)),
                         "spreads that can lose $105.00 together would be over the $100 position cap")
        self.assertFalse(fits_caps(v, D(75), D(100), held_max_loss=D(35)))

    def test_a_real_options_bunt_is_one_spread_under_forty_dollars(self):
        """What an $80 options bunt is shown today (CONTRACT.md: $39.99 a contract) is what a
        spread's debit must fit: one 0.39 spread fits, one 0.40 does not."""
        self.assertTrue(fits_caps(parse_vertical(VENUE, spec(limit_price=0.39)), D("39.99"), D("39.99")))
        self.assertFalse(fits_caps(parse_vertical(VENUE, spec(limit_price=0.40)), D("39.99"), D("39.99")))

    def test_a_close_always_fits(self):
        v = parse_vertical(VENUE, spec(side="sell", quantity=9, limit_price=0.10))
        self.assertIsNone(cap_refusal(v, D(1), D(1), held_max_loss=D(1000)))


class OneSpreadOneTrade(unittest.TestCase):
    """`count_trades` over per-leg fills. The shape (one FILL activity a leg, with the leg's own OCC
    symbol, side and quantity) is what Alpaca's docs describe and nothing here has seen."""

    def open(self, at="2026-10-01T14:00:00.000Z", long=C13, short=C14, quantity="1"):
        return [leg(long, "buy", quantity, at, "0.50"), leg(short, "sell", quantity, at, "0.15")]

    def close(self, at="2026-10-02T14:00:00.000Z", long=C13, short=C14, quantity="1"):
        return [leg(long, "sell", quantity, at, "0.70", "o2"), leg(short, "buy", quantity, at, "0.20", "o2")]

    def test_an_open_and_a_close_are_one_trade_never_two(self):
        self.assertEqual(count_trades(self.open() + self.close()), 1)

    def test_an_open_spread_is_no_trade_yet(self):
        self.assertEqual(count_trades(self.open()), 0)
        self.assertEqual(count_trades([]), 0)

    def test_two_spreads_in_turn_are_two_trades(self):
        fills = self.open() + self.close() + self.open("2026-10-03T14:00:00.000Z") + self.close("2026-10-04T14:00:00.000Z")
        self.assertEqual(count_trades(fills), 2)

    def test_a_lone_contract_bought_and_sold_is_not_a_spread(self):
        """The allocator's `closed_trades` counts it, as today; this counter never does."""
        fills = [leg(C13, "buy"), leg(C13, "sell", at="2026-10-02T14:00:00.000Z")]
        self.assertEqual(count_trades(fills), 0)

    def test_partial_fills_of_a_leg_are_still_one_trade(self):
        fills = (self.open(quantity="1") + self.open("2026-10-01T14:00:01.000Z", quantity="1")
                 + [leg(C13, "sell", "2", "2026-10-02T14:00:00.000Z", order_id="o2"), leg(C14, "buy", "1", "2026-10-02T14:00:00.000Z", order_id="o2"),
                    leg(C14, "buy", "1", "2026-10-02T14:00:02.000Z", order_id="o2")])
        self.assertEqual(count_trades(fills), 1)

    def test_a_leg_taken_away_first_still_ends_as_one_trade(self):
        """A short leg assigned away, then the long leg sold on its own: one spread, one trade."""
        fills = self.open() + [leg(C14, "buy", at="2026-10-02T13:00:00.000Z", order_id="assignment"),
                               leg(C13, "sell", at="2026-10-02T15:00:00.000Z", order_id="o2")]
        self.assertEqual(count_trades(fills), 1)

    def test_fills_are_read_in_time_order_whatever_order_they_arrive(self):
        fills = self.close() + self.open()
        self.assertEqual(count_trades(fills), 1)

    def test_another_underlying_expiry_or_right_is_another_spread(self):
        fills = self.open() + self.open(long=SOFI13, short="SOFI261016C00014000") + self.close()
        self.assertEqual(count_trades(fills), 1)  # F closed, SOFI still open
        fills += self.open(long=P14, short=P13) + self.close(long=P14, short=P13)
        self.assertEqual(count_trades(fills), 2)

    def test_fills_in_other_asset_classes_are_ignored(self):
        stock = Fill(id="s", order_id="o", desk_id="", instrument=instrument_for(VENUE, {"symbol": "F"}), side="buy",
                     quantity=D(1), price=D(13), fee=D(0), at="2026-10-01T14:00:00.000Z")
        self.assertEqual(count_trades([stock] + self.open() + self.close()), 1)


class TheOrderShape(unittest.TestCase):
    """The multi-leg body Alpaca documents (and the gateway refuses, #187): pinned so the adapter
    change the design describes has a spec, and so this module never builds a single-leg order."""

    def test_an_opening_spread_is_one_mleg_limit_order_with_two_legs_and_no_top_level_symbol(self):
        body = mleg_body(parse_vertical(VENUE, spec(quantity=2)), client_order_id="oi-abc")
        self.assertEqual(body["order_class"], "mleg")
        self.assertNotIn("symbol", body)
        self.assertEqual((body["qty"], body["type"], body["limit_price"], body["time_in_force"], body["client_order_id"]),
                         ("2", "limit", "0.35", "day", "oi-abc"))
        self.assertEqual(body["legs"], [
            {"symbol": C13, "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
            {"symbol": C14, "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"},
        ])

    def test_a_close_reverses_both_legs_and_names_the_credit(self):
        body = mleg_body(parse_vertical(VENUE, spec(side="sell", limit_price=0.60)), client_order_id="oi-def")
        self.assertEqual(body["legs"], [
            {"symbol": C13, "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_close"},
            {"symbol": C14, "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_close"},
        ])
        self.assertEqual(body["limit_price"], "-0.60")  # Alpaca's documented sign: a credit is negative (unverified)


class OnePosition(unittest.TestCase):
    """Sept 25, 2026: a spread is held as ONE long option-class instrument priced at its net."""

    def vertical(self, long=C13, short=C14, **kw):
        return parse_vertical(VENUE, spec(long, short, **kw))

    def test_the_instrument_names_both_legs_and_keys_apart_from_the_long_leg(self):
        inst = verticals.spread_instrument(self.vertical(), "options-shadow")
        self.assertEqual((inst.asset_class, inst.symbol, inst.venue, inst.expiry, inst.right), ("option", "F", "options-shadow", "2026-10-16", "call"))
        self.assertEqual((inst.strike, inst.multiplier, inst.market_id), (D("13"), D("100"), f"{C13}/{C14}"))
        single = instrument_for("options-shadow", {"occ": C13})
        self.assertNotEqual(inst.key, single.key)
        self.assertTrue(verticals.is_spread(inst))
        self.assertFalse(verticals.is_spread(single))
        wider = verticals.spread_instrument(self.vertical(C13, C15), "options-shadow")
        self.assertNotEqual(inst.key, wider.key)

    def test_legs_and_vertical_round_trip(self):
        inst = verticals.spread_instrument(self.vertical(P14, P13), "options-shadow")
        long, short = verticals.legs_of(inst)
        self.assertEqual((alpaca_symbol(long), alpaca_symbol(short)), (P14, P13))
        self.assertEqual(long.venue, "options-shadow")
        closing = verticals.vertical_of(inst, quantity=2, net="0.41", side="sell", reason="take profit")
        self.assertEqual((closing.side, closing.quantity, closing.net_debit, closing.width), ("sell", D(2), D("0.41"), D(1)))

    def test_a_reversed_name_can_never_be_traded(self):
        inst = verticals.spread_instrument(self.vertical(), "options-shadow")
        reversed_ = type(inst)("option", "F", "options-shadow", multiplier=100, expiry=inst.expiry, strike=D(14), right="call", market_id=f"{C14}/{C13}")
        self.assertTrue(verticals.is_spread(reversed_))
        with self.assertRaisesRegex(ValueError, "credit spread"):
            verticals.vertical_of(reversed_, quantity=1, net="0.30", side="buy")
        with self.assertRaises(ValueError):
            verticals.legs_of(instrument_for("options-shadow", {"occ": C13}))

    def test_the_touch_is_what_both_legs_trade_at_at_once(self):
        self.assertEqual(verticals.spread_quote("0.80", "0.85", "0.40", "0.44"), (D("0.36"), D("0.45")))
        self.assertEqual(verticals.spread_quote("0.10", "0.85", "0.40", "0.44"), (D(0), D("0.45")))  # never under zero
        self.assertEqual(verticals.spread_quote(None, "0.85", "0.40", None), (None, D("0.45")))

    def test_intrinsic_is_between_zero_and_the_width(self):
        calls = verticals.spread_instrument(self.vertical(), "options-shadow")
        self.assertEqual([verticals.intrinsic(calls, x) for x in ("12", "13.40", "20")], [D(0), D("0.40"), D(1)])
        puts = verticals.spread_instrument(self.vertical(P14, P13), "options-shadow")
        self.assertEqual([verticals.intrinsic(puts, x) for x in ("15", "13.75", "10")], [D(0), D("0.25"), D(1)])


class Boundaries(unittest.TestCase):
    def test_the_module_imports_no_house_book_or_gateway_code(self):
        source = Path(verticals.__file__).read_text(encoding="utf-8")
        for forbidden in ("house", "book", "allocator", "live_trading", "gateway"):
            self.assertNotRegex(source, rf"^\s*(from|import)\s+[\w.]*\b{forbidden}\b", forbidden)


if __name__ == "__main__":
    unittest.main()
