"""Kalshi charges makers on some series (the big leagues' winner, spread and total markets).

Found on Sept 19, 2026 by replaying a football founder over a real week: the replay charged a
resting fill nothing anywhere, so every sports replay was flattered by the fee it did not pay.
"""

import unittest

from league.replay import _Account, kalshi_maker_fee, kalshi_taker_fee
from league.tapes import _maker_fee_series


class MakerFees(unittest.TestCase):
    def account(self, series=("KXNFLGAME",)):
        return _Account("kalshi", 200.0, {"max_position_usd": 100.0, "max_order_usd": 75.0}, {}, False, list(series))

    def test_the_maker_fee_is_a_quarter_of_the_taker_fee_rounded_up_to_a_hundredth_of_a_cent(self):
        self.assertEqual(kalshi_maker_fee(10, 0.93), 0.0114)  # 0.0175 x 10 x 0.93 x 0.07 = 0.0113925
        self.assertEqual(kalshi_taker_fee(10, 0.93), 0.0456)

    def test_a_resting_fill_pays_on_a_series_that_charges_makers_and_nothing_elsewhere(self):
        account = self.account()
        self.assertEqual(account.fee("KXNFLGAME-26SEP20CLETB-TB|yes", 10, 0.93, "maker"), 0.0114)
        self.assertEqual(account.fee("KXNFLTD-26SEP20CLETB-X|no", 10, 0.93, "maker"), 0.0)
        self.assertEqual(account.fee("KXHIGHNY-26SEP20-T78|yes", 10, 0.93, "maker"), 0.0)

    def test_a_taker_pays_the_taker_fee_everywhere(self):
        account = self.account()
        for key in ("KXNFLGAME-26SEP20CLETB-TB|yes", "KXHIGHNY-26SEP20-T78|yes"):
            self.assertEqual(account.fee(key, 10, 0.93, "taker"), 0.0456)

    def test_a_tape_without_the_list_charges_makers_nothing(self):
        self.assertEqual(self.account(series=()).fee("KXNFLGAME-26SEP20CLETB-TB|yes", 10, 0.93, "maker"), 0.0)

    def test_the_tape_names_the_series_that_charge_makers_from_the_fee_file(self):
        self.assertEqual(_maker_fee_series(["KXNFLGAME", "KXNFLTD", "KXHIGHNY", "KXEPLGAME", "KXEPLTOTAL"]), ["KXNFLGAME", "KXEPLGAME"])


if __name__ == "__main__":
    unittest.main()
