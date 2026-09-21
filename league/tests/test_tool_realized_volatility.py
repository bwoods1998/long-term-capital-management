"""Known-value tests for the pure sampled realized-volatility estimator."""

import json
import math
import unittest

from league.tools.realized_volatility import realized_volatility


class TestRealizedVolatility(unittest.TestCase):
    def test_geometric_path_is_not_demeaned_or_annualized(self):
        result = realized_volatility([1.0, 2.0, 4.0])
        self.assertEqual(result['n_closes'], 3)
        self.assertEqual(result['n_returns'], 2)
        self.assertAlmostEqual(result['realized_variance'], 2 * math.log(2) ** 2)
        self.assertAlmostEqual(result['realized_volatility'], math.sqrt(2) * math.log(2))

    def test_round_trip_has_positive_variation(self):
        result = realized_volatility([1.0, 2.0, 1.0])
        self.assertAlmostEqual(result['realized_variance'], 2 * math.log(2) ** 2)
        self.assertGreater(result['realized_volatility'], 0.0)

    def test_unequal_returns(self):
        result = realized_volatility([100.0, 110.0, 99.0])
        expected = math.log(1.1) ** 2 + math.log(0.9) ** 2
        self.assertAlmostEqual(result['realized_variance'], expected)
        self.assertAlmostEqual(result['realized_volatility'], math.sqrt(expected))

    def test_flat_path(self):
        result = realized_volatility([7, 7, 7])
        self.assertEqual(result['realized_variance'], 0.0)
        self.assertEqual(result['realized_volatility'], 0.0)
        self.assertEqual(result['n_returns'], 2)

    def test_insufficient_samples_are_not_zero_volatility(self):
        for prices in ([], [100.0]):
            with self.subTest(prices=prices):
                result = realized_volatility(prices)
                self.assertEqual(result['n_closes'], len(prices))
                self.assertEqual(result['n_returns'], 0)
                self.assertIsNone(result['realized_variance'])
                self.assertIsNone(result['realized_volatility'])

    def test_one_return(self):
        result = realized_volatility([4.0, 2.0])
        self.assertEqual(result['n_returns'], 1)
        self.assertAlmostEqual(result['realized_volatility'], math.log(2))

    def test_scale_invariance(self):
        base = realized_volatility([1.0, 2.0, 1.0])
        scaled = realized_volatility([100.0, 200.0, 100.0])
        self.assertAlmostEqual(base['realized_variance'], scaled['realized_variance'])

    def test_iterable_and_no_input_mutation(self):
        prices = [100, 101, 99]
        before = list(prices)
        result = realized_volatility(prices)
        self.assertEqual(prices, before)
        self.assertEqual(result, realized_volatility(value for value in prices))

    def test_extreme_finite_prices(self):
        expected = 600 * math.log(10)
        for prices in ([1e-300, 1e300], [1e300, 1e-300]):
            with self.subTest(prices=prices):
                result = realized_volatility(prices)
                self.assertTrue(math.isfinite(result['realized_variance']))
                self.assertAlmostEqual(result['realized_volatility'] / expected, 1.0)

    def test_small_relative_change_at_large_price(self):
        first = 1e200
        second = first * (1 + 1e-12)
        expected = math.log1p((second - first) / first)
        result = realized_volatility([first, second])
        self.assertGreater(result['realized_volatility'], 0.0)
        self.assertAlmostEqual(result['realized_volatility'] / expected, 1.0)

    def test_rejects_invalid_prices_even_without_a_return(self):
        invalid = [0, -1, float('nan'), float('inf'), float('-inf'),
                   True, False, '100', None, 10 ** 400]
        for price in invalid:
            with self.subTest(price=repr(price)):
                with self.assertRaises(ValueError):
                    realized_volatility([price])
                with self.assertRaises(ValueError):
                    realized_volatility([100.0, price])

    def test_results_are_json_safe(self):
        for prices in ([], [1.0], [1.0, 2.0, 1.0]):
            result = realized_volatility(prices)
            self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)


if __name__ == '__main__':
    unittest.main()
