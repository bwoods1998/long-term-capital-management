"""Corporate actions and dividends (`league/equity/actions.py`, A8.10): a dividend split pro rata by quantity (a
withholding negative, shares outside the book unattributed), a split keeping each lot's notional, cash in lieu, a
spin-off, a cash-out merger, a rename, and the freeze for anything the row does not describe or any other type
touching a held symbol. Rows are invented, in Alpaca's documented non-trade activity shape."""

import json
import unittest
from decimal import Decimal as D

from league.equity import actions as A


def lot(lid, qty, *, symbol="SPY", px="500", notional=None):
    qty, px = D(qty), D(px)
    return {"lid": lid, "symbol": symbol, "qty": str(qty), "opened_qty": str(qty), "entry_px": str(px),
            "entry_notional": str(notional if notional is not None else qty * px)}


def activity(kind, *, symbol="SPY", net="0", qty=None, **extra):
    row = {"id": f"{kind}-1", "activity_type": kind, "date": "2026-10-09", "symbol": symbol, "net_amount": net,
           "status": "executed"}
    if qty is not None:
        row["qty"] = qty
    row.update(extra)
    return row


class Dividends(unittest.TestCase):
    def test_pro_rata_by_quantity_nothing_lost(self):
        b = A.book_activity(activity("DIV", net="4.50", qty="3"), [lot(1, "1"), lot(2, "2"), lot(3, "5", symbol="QQQ")])
        self.assertEqual(b.kind, "dividend")
        self.assertEqual(b.per_lot, {1: {"div": D("1.5"), "cash": D("1.5")}, 2: {"div": D("3.0"), "cash": D("3.0")}})
        self.assertEqual(b.unattributed, 0)
        self.assertEqual(b.day, "2026-10-09")

    def test_the_rounding_remainder_goes_to_the_largest_lot(self):
        b = A.book_activity(activity("DIV", net="1.00"), [lot(1, "1"), lot(2, "1"), lot(3, "1")])
        self.assertEqual(sum(c["div"] for c in b.per_lot.values()), D("1.00"))
        self.assertEqual(b.per_lot[1]["div"], D("0.333334"))

    def test_shares_outside_the_book_are_unattributed(self):
        # The account held 3 shares, the book 1 (two were an assignment's): the book takes a third.
        b = A.book_activity(activity("DIV", net="3.00", qty="3"), [lot(1, "1")])
        self.assertEqual(b.per_lot[1]["div"], D("1.000000"))
        self.assertEqual(b.unattributed, D("2.000000"))

    def test_a_withholding_is_negative(self):
        b = A.book_activity(activity("DIVNRA", net="-0.30", qty="2"), [lot(1, "2")])
        self.assertEqual(b.per_lot[1], {"div": D("-0.30"), "cash": D("-0.30")})
        self.assertIn("withholding", b.why)

    def test_a_dividend_no_lot_held(self):
        b = A.book_activity(activity("DIV", net="2"), [])
        self.assertEqual((b.kind, b.per_lot, b.unattributed), ("dividend", {}, D("2")))

    def test_the_ex_date_when_the_row_states_one(self):
        self.assertEqual(A.book_activity(activity("DIV", net="1", ex_date="2026-09-30"), [lot(1, "1")]).day, "2026-09-30")


class Splits(unittest.TestCase):
    def test_a_split_keeps_each_lots_notional(self):
        b = A.book_activity(activity("SSP", ratio="2"), [lot(1, "1.5", px="600"), lot(2, "0.25", px="580")])
        self.assertEqual(b.kind, "split")
        self.assertEqual(b.per_lot[1], {"qty": D("3.000000000"), "opened_qty": D("3.000000000"), "entry_px": D("300.000000")})
        self.assertEqual(b.per_lot[2]["qty"], D("0.500000000"))
        self.assertEqual(b.per_lot[2]["entry_px"] * b.per_lot[2]["opened_qty"], D("145.0000000"))

    def test_a_reverse_split_from_the_rates(self):
        b = A.book_activity(activity("SSP", new_rate="1", old_rate="10"), [lot(1, "5", px="10")])
        self.assertEqual((b.per_lot[1]["qty"], b.per_lot[1]["entry_px"]), (D("0.500000000"), D("100.000000")))

    def test_a_split_floors_to_nine_places(self):
        b = A.book_activity(activity("SSP", ratio="3"), [lot(1, "0.3333333333")])
        self.assertEqual(b.per_lot[1]["qty"], D("0.999999999"))

    def test_a_split_with_cash_in_lieu(self):
        b = A.book_activity(activity("SSP", ratio="0.1", net="1.20"), [lot(1, "1"), lot(2, "3")])
        self.assertEqual(b.per_lot[1]["cash"] + b.per_lot[2]["cash"], D("1.20"))
        self.assertIn("cash in lieu", b.why)

    def test_a_split_without_a_ratio_freezes(self):
        b = A.book_activity(activity("SSP"), [lot(1, "1")])
        self.assertEqual((b.kind, b.per_lot), ("freeze", {}))


class OtherActions(unittest.TestCase):
    def test_cash_in_lieu_on_its_own_row(self):
        b = A.book_activity(activity("CIL", net="0.75"), [lot(1, "1")])
        self.assertEqual((b.kind, b.per_lot), ("cash_in_lieu", {1: {"cash": D("0.75")}}))

    def test_a_spin_off_keeps_the_lots(self):
        b = A.book_activity(activity("SSO", net="0"), [lot(1, "1")])
        self.assertEqual((b.kind, b.per_lot), ("spinoff", {}))
        self.assertIn("outside the book", b.why)

    def test_a_cash_merger_closes_the_lots(self):
        b = A.book_activity(activity("MA", symbol="XOM", net="150", qty="-1.5"), [lot(1, "1.5", symbol="XOM", px="100")])
        self.assertEqual(b.kind, "cash_in_lieu")
        self.assertEqual(b.per_lot[1], {"cash": D("150"), "qty": D(0)})

    def test_a_reorganisation_at_a_ratio(self):
        b = A.book_activity(activity("REORG", symbol="XOM", ratio="0.5"), [lot(1, "2", symbol="XOM", px="100")])
        self.assertEqual((b.kind, b.per_lot[1]["qty"], b.per_lot[1]["entry_px"]), ("split", D("1.000000000"), D("200.000000")))

    def test_a_merger_the_row_does_not_describe_freezes(self):
        self.assertEqual(A.book_activity(activity("MA", symbol="XOM"), [lot(1, "1", symbol="XOM")]).kind, "freeze")

    def test_a_rename(self):
        b = A.book_activity(activity("NC", new_symbol="ABCD"), [lot(1, "1")])
        self.assertEqual((b.kind, b.new_symbol), ("rename", "ABCD"))
        self.assertEqual(A.book_activity(activity("NC"), [lot(1, "1")]).kind, "freeze")

    def test_any_other_type_touching_a_held_symbol_freezes(self):
        b = A.book_activity(activity("SC"), [lot(1, "1")])
        self.assertEqual(b.kind, "freeze")
        self.assertIn("A8.10", b.why)

    def test_a_row_on_a_symbol_the_book_does_not_hold(self):
        for kind in ("SSP", "SC", "MA"):
            self.assertEqual(A.book_activity(activity(kind, symbol="TLT", ratio="2"), [lot(1, "1")]).kind, "none")

    def test_a_booking_is_json_safe(self):
        b = A.book_activity(activity("DIV", net="4.50", qty="3"), [lot(1, "1"), lot(2, "2")])
        back = json.loads(json.dumps(b.as_dict()))
        self.assertEqual(back["per_lot"]["1"], {"div": "1.500000", "cash": "1.500000"})

    def test_the_types(self):
        self.assertEqual(A.TYPES, A.DIVIDENDS + A.ACTIONS)
        self.assertFalse(set(A.WATCH) & set(A.TYPES))
        self.assertIn("CIL", A.WATCH)


if __name__ == "__main__":
    unittest.main()
