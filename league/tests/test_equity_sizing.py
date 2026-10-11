"""THE ONE SIZING FUNCTION of an equity entry (`league/equity/sizing.py` `size_entry`; release E1, INTERFACES 7.4): a
table of cases, one for each rule that can bind, as the book (live figures, the shared budget's room) and the engine (E
= the sleeve, no budget, available cash = the sleeve's) call it. Invented figures only; standard library only."""

import unittest
from dataclasses import replace
from decimal import Decimal as D

from league.equity import config
from league.equity.sizing import CAPS, Sized, SizingInputs, size_entry

#: A House at E = $2,000 with a sleeve of $500 (both invented: `size_entry` takes the sleeve's dollars as a fact it is
#: given), nothing held, plenty of cash and budget. The table's own Probe sleeve (0.50 x E since the captain's A20, Oct
#: 11, 2026) is sized through this same function in league/tests/test_equity_sleeve.py.
LIVE = SizingInputs(symbol="SPY", klass="etf", share=D("0.5"), usd=None, limit_price=D("100.00"), E=D("2000"),
                    sleeve_equity=D("500"), sleeve_free_cash=D("500"), sleeve_symbol_value=D("0"),
                    position_share=D("0.50"), account_symbol_value=D("0"), invested_now=D("0"),
                    invested_share=D("1.00"), available_cash=D("1500"), cash=D("1600"), any_short=False,
                    budget_room=D("400"), weight=D("0.20"), min_order_usd=D("10"))


def sized(**over) -> Sized:
    return size_entry(replace(LIVE, **over))


class Bindings(unittest.TestCase):
    """Each binding: the dollars, the share count (floored to `config.QTY_PLACES`) and the rule named."""

    def test_the_table(self):
        cases = (
            # (changes, usd, binding)
            ({}, "250", "intent"),                                                     # half of a $500 sleeve
            ({"usd": D("120"), "share": None}, "120", "intent"),                       # an intent in dollars
            ({"account_symbol_value": D("900")}, "100", "instrument"),                 # 0.50 x 2000 - 900
            ({"klass": "stock", "symbol": "AAPL", "position_share": D("0.20"), "share": D("1"),
              "sleeve_equity": D("2000"), "sleeve_free_cash": D("2000"), "budget_room": D("400"),
              "weight": D("0.40")}, "400", "instrument"),                              # 0.20 x 2000 = 400 < the budget's 1000
            ({"share": D("1"), "sleeve_symbol_value": D("100")}, "150", "sleeve_cap"),  # 0.50 x 500 - 100
            ({"sleeve_free_cash": D("80")}, "80", "sleeve_cash"),
            ({"invested_now": D("1900")}, "100", "invested"),                          # 1.00 x 2000 - 1900
            ({"invested_share": D("0.50"), "invested_now": D("900")}, "100", "invested"),
            ({"available_cash": D("60")}, "60", "cash"),
            ({"budget_room": D("30")}, "150", "budget"),                               # 30 / 0.20
            ({"klass": "stock", "symbol": "AAPL", "position_share": D("0.20"), "budget_room": D("30"),
              "weight": D("0.40")}, "75", "budget"),                                   # 30 / 0.40, under the sleeve's 100
        )
        for over, usd, binding in cases:
            out = sized(**over)
            self.assertEqual((out.usd, out.binding), (D(usd), binding), (over, out))
            self.assertEqual(out.qty, (D(usd) / D("100.00")).quantize(D("0.000001")))
            self.assertTrue(out.reason)

    def test_refusals_come_first(self):
        out = sized(cash=D("-0.01"))
        self.assertEqual((out.usd, out.qty, out.binding), (D(0), D(0), "cash_negative"))
        self.assertIn("borrowing", out.reason)
        out = sized(any_short=True)
        self.assertEqual((out.usd, out.qty, out.binding), (D(0), D(0), "short_held"))
        out = sized(cash=D("-5"), any_short=True)
        self.assertEqual(out.binding, "cash_negative", "a negative cash is named first")
        self.assertEqual(sized(cash=D("0")).binding, "intent", "zero cash is not negative (the cash cap is separate)")

    def test_a_cap_that_leaves_nothing_refuses_under_its_own_name(self):
        for over, binding in (({"account_symbol_value": D("1000")}, "instrument"),
                              ({"account_symbol_value": D("1200")}, "instrument"),
                              ({"sleeve_symbol_value": D("250")}, "sleeve_cap"),
                              ({"sleeve_free_cash": D("0")}, "sleeve_cash"),
                              ({"invested_now": D("2100")}, "invested"),
                              ({"available_cash": D("-40")}, "cash"),
                              ({"budget_room": D("0")}, "budget"),
                              ({"budget_room": D("-12")}, "budget")):
            out = sized(**over)
            self.assertEqual((out.usd, out.qty, out.binding), (D(0), D(0), binding), over)
            self.assertTrue(out.reason.startswith("refused: "), out.reason)

    def test_under_the_minimum_is_skipped_and_says_what_cut_it(self):
        out = sized(share=D("0.01"))                                          # $5 asked
        self.assertEqual((out.usd, out.qty, out.binding), (D(0), D(0), "min_order"))
        self.assertEqual(out.reason, "skipped: $5.00 is under the $10.00 minimum")
        out = sized(available_cash=D("9.99"))
        self.assertEqual((out.usd, out.binding), (D(0), "min_order"))
        self.assertIn("House-wide available cash", out.reason)
        out = sized(budget_room=D("1.99"))                                    # 1.99 / 0.20 = 9.95
        self.assertEqual(out.binding, "min_order")
        self.assertIn("shared loss budget", out.reason)
        self.assertEqual(sized(available_cash=D("10")).usd, D("10"), "exactly the minimum goes")

    def test_the_share_count_is_floored_and_never_spends_above_the_target(self):
        out = sized(limit_price=D("333.3333"), usd=D("250"), share=None)
        self.assertEqual(out.qty, D("0.750000"))
        self.assertEqual(out.usd, D("0.750000") * D("333.3333"))
        self.assertLessEqual(out.usd, D("250"))
        out = sized(limit_price=D("7.0001"), usd=D("10.000001"), share=None)
        self.assertEqual((out.qty, out.binding), (D(0), "min_order"), "floored under $10: skipped")
        for limit in ("0.9999", "1", "17.31", "612.4567", "4999.99"):
            out = sized(limit_price=D(limit))
            self.assertEqual(out.qty, out.qty.quantize(D(1).scaleb(-config.QTY_PLACES)), limit)
            self.assertLessEqual(out.usd, D("250"), limit)
            self.assertGreater(out.usd + D(limit) * D("0.000001"), D("250") - D("0.0000001"), limit)

    def test_ties_name_the_earlier_rule(self):
        """The Gym passes the sleeve's free cash as the available cash: a tie names the sleeve's."""
        self.assertEqual(list(CAPS), ["instrument", "sleeve_cap", "sleeve_cash", "invested", "cash", "budget"])
        out = sized(sleeve_free_cash=D("60"), available_cash=D("60"))
        self.assertEqual((out.usd, out.binding), (D("60"), "sleeve_cash"))
        out = sized(share=D("1"), account_symbol_value=D("750"))            # instrument 250 == sleeve cap 250
        self.assertEqual((out.usd, out.binding), (D("250"), "instrument"))
        self.assertEqual(sized(usd=D("250"), share=None, sleeve_free_cash=D("250")).binding, "intent",
                         "a cap equal to the target does not cut it")


class TheGym(unittest.TestCase):
    """The engine's call: E = the sleeve (`config.SLEEVE_USD`), no budget, the sleeve's free cash as available cash, no
    account to be short or below zero."""

    def gym(self, **over):
        x = SizingInputs(symbol="QQQ", klass="etf", share=D("1"), usd=None, limit_price=D("50"), E=config.SLEEVE_USD,
                         sleeve_equity=config.SLEEVE_USD, sleeve_free_cash=config.SLEEVE_USD, sleeve_symbol_value=D("0"),
                         position_share=config.POSITION_SHARE["etf"], account_symbol_value=D("0"), invested_now=D("0"),
                         invested_share=D("1.00"), available_cash=config.SLEEVE_USD, cash=config.SLEEVE_USD,
                         any_short=False, budget_room=None, weight=D("0.20"), min_order_usd=D("10"))
        return size_entry(replace(x, **over))

    def test_the_sleeves_caps_bind_and_no_budget_is_read(self):
        out = self.gym()
        self.assertEqual((out.usd, out.binding), (D("500"), "instrument"), "0.50 of the sleeve")
        out = self.gym(share=D("0.3"))
        self.assertEqual((out.usd, out.binding), (D("300"), "intent"))
        out = self.gym(sleeve_free_cash=D("120"), available_cash=D("120"))
        self.assertEqual((out.usd, out.binding), (D("120"), "sleeve_cash"))
        out = self.gym(klass="stock", symbol="MSFT", position_share=config.POSITION_SHARE["stock"])
        self.assertEqual((out.usd, out.binding), (D("200"), "instrument"))


class CodeCeilings(unittest.TestCase):
    def test_a_position_share_above_the_owners_line_is_read_at_the_line(self):
        out = sized(share=D("1"), position_share=D("0.90"), sleeve_equity=D("2000"), sleeve_free_cash=D("2000"),
                    budget_room=None)
        self.assertEqual((out.usd, out.binding), (D("1000"), "instrument"), "0.50 x E, whatever was passed")
        out = sized(klass="stock", symbol="NVDA", share=D("1"), position_share=D("0.50"), sleeve_equity=D("2000"),
                    sleeve_free_cash=D("2000"), budget_room=None, weight=D("0.40"))
        self.assertEqual((out.usd, out.binding), (D("400"), "instrument"), "0.20 x E for a stock")

    def test_malformed_facts_are_refused(self):
        for over in ({"klass": "bond"}, {"share": D("0")}, {"share": D("1.01")}, {"share": D("-0.5")},
                     {"usd": D("100")}, {"share": None}, {"share": None, "usd": D("0")}, {"limit_price": D("0")},
                     {"limit_price": D("-1")}, {"weight": D("0")}, {"E": 2000.0}, {"cash": "1600"},
                     {"available_cash": D("NaN")}, {"budget_room": D("Infinity")}, {"any_short": 0},
                     {"min_order_usd": None}):
            with self.assertRaises(ValueError, msg=over):
                sized(**over)


if __name__ == "__main__":
    unittest.main()
