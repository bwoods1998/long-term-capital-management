"""Known-value and boundary tests for the pure realized-volatility helper."""

import math
import unittest

from league.tools.realized_volatility import realized_volatility


class RealizedVolatilityTests(unittest.TestCase):
    def test_known_log_returns(self):
        # Log returns are +0.10 and -0.05; RV is sqrt(0.0125).
        prices = [1.0, math.exp(0.10), math.exp(0.05)]
        self.assertAlmostEqual(
            realized_volatility(prices), math.sqrt(0.0125), places=14
        )

    def test_constant_prices(self):
        self.assertEqual(realized_volatility([100, 100, 100, 100]), 0.0)

    def test_one_return(self):
        self.assertAlmostEqual(
            realized_volatility([1, 2]), math.log(2), places=14
        )
        self.assertAlmostEqual(
            realized_volatility([2, 1]), math.log(2), places=14
        )

    def test_trend_is_not_demeaned(self):
        # Identical nonzero returns have zero sample standard deviation,
        # but strictly positive realized volatility.
        self.assertAlmostEqual(
            realized_volatility([1, 2, 4]),
            math.sqrt(2) * math.log(2),
            places=14,
        )

    def test_dimensionless_scale_invariance(self):
        self.assertAlmostEqual(
            realized_volatility([1, 1.5, 1.2, 2]),
            realized_volatility([100, 150, 120, 200]),
            places=13,
        )

    def test_coarse_sampling_cannot_recover_missing_variation(self):
        # Equal endpoints conceal the intervening move in a coarse sample.
        self.assertEqual(realized_volatility([1, 1]), 0.0)
        self.assertAlmostEqual(
            realized_volatility([1, math.e, 1]), math.sqrt(2), places=14
        )

    def test_input_is_preserved(self):
        prices = [100, 105, 103]
        before = prices[:]
        first = realized_volatility(prices)
        self.assertEqual(prices, before)
        self.assertEqual(first, realized_volatility(prices))

    def test_accepts_iterable(self):
        self.assertAlmostEqual(
            realized_volatility(iter([1, 2, 4])),
            math.sqrt(2) * math.log(2),
            places=14,
        )

    def test_extreme_finite_prices_do_not_require_finite_ratio(self):
        self.assertAlmostEqual(
            realized_volatility([1e-300, 1e300]),
            600 * math.log(10),
            places=10,
        )

    def test_insufficient_observations(self):
        for prices in ([], [100]):
            with self.subTest(prices=prices):
                with self.assertRaises(ValueError):
                    realized_volatility(prices)

    def test_rejects_invalid_prices(self):
        invalid = [
            0,
            -1,
            float('nan'),
            float('inf'),
            -float('inf'),
            True,
            False,
            '100',
            None,
            10 ** 400,
        ]
        for price in invalid:
            with self.subTest(price=price):
                with self.assertRaises(ValueError):
                    realized_volatility([100, price])


if __name__ == '__main__':
    unittest.main()
