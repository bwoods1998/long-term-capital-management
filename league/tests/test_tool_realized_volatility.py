import math
import unittest

from league.tools.realized_volatility import realized_volatility


START = '2026-09-21T00:00:00Z'


def minute_bars(closes):
    return [
        {'t': '2026-09-21T00:%02d:00Z' % index, 'c': close}
        for index, close in enumerate(closes)
    ]


class TestRealizedVolatility(unittest.TestCase):
    def test_known_value_without_demeaning(self):
        result = realized_volatility(
            minute_bars([100, 200, 400]), START,
            '2026-09-21T00:02:00Z', 60, 'end')
        expected = 2 * math.log(2) ** 2
        self.assertTrue(result['complete'])
        self.assertEqual(result['n_returns'], 2)
        self.assertEqual(result['expected_returns'], 2)
        self.assertAlmostEqual(result['variance'], expected, places=12)
        self.assertAlmostEqual(result['volatility'], math.sqrt(expected), places=12)

    def test_round_trip_has_nonzero_variation(self):
        result = realized_volatility(
            minute_bars([100, 200, 100]), START,
            '2026-09-21T00:02:00Z', 60, 'end')
        self.assertAlmostEqual(result['variance'], 2 * math.log(2) ** 2, places=12)

    def test_fifteen_returns_require_sixteen_prices(self):
        rows = minute_bars([100 * math.exp(0.01 * index) for index in range(16)])
        result = realized_volatility(
            rows, START, '2026-09-21T00:15:00Z', 60, 'end')
        self.assertTrue(result['complete'])
        self.assertEqual(result['n_returns'], 15)
        self.assertEqual(result['expected_returns'], 15)
        self.assertAlmostEqual(result['variance'], 0.0015, places=12)
        self.assertAlmostEqual(result['volatility'], math.sqrt(0.0015), places=12)

    def test_constant_prices_are_zero_not_missing(self):
        result = realized_volatility(
            minute_bars([100, 100, 100]), START,
            '2026-09-21T00:02:00Z', 60, 'end')
        self.assertTrue(result['complete'])
        self.assertEqual(result['variance'], 0.0)
        self.assertEqual(result['volatility'], 0.0)

    def test_start_stamps_exclude_unfinished_bar(self):
        rows = [
            {'t': '2026-09-20T23:59:00Z', 'c': 100},
            {'t': '2026-09-21T00:00:00Z', 'c': 200},
            {'t': '2026-09-21T00:01:00Z', 'c': 100},
            {'t': '2026-09-21T00:02:00Z', 'c': float('nan')},
        ]
        result = realized_volatility(
            rows, START, '2026-09-21T00:02:59Z', 60, 'start')
        control = realized_volatility(
            rows[:3], START, '2026-09-21T00:02:59Z', 60, 'start')
        self.assertEqual(result, control)
        self.assertEqual(result['expected_returns'], 2)
        self.assertAlmostEqual(result['variance'], 2 * math.log(2) ** 2, places=12)

    def test_prefix_does_not_use_future_window(self):
        result = realized_volatility(
            minute_bars([100, 200, 100]), START,
            '2026-09-21T00:01:00Z', 60, 'end')
        self.assertTrue(result['complete'])
        self.assertEqual(result['n_returns'], 1)
        self.assertAlmostEqual(result['variance'], math.log(2) ** 2, places=12)

    def test_missing_baseline_and_gap_are_not_bridged(self):
        rows = minute_bars([100, 200, 400])
        for supplied, count in ((rows[1:], 1), (rows[::2], 0)):
            with self.subTest(supplied=supplied):
                result = realized_volatility(
                    supplied, START, '2026-09-21T00:02:00Z', 60, 'end')
                self.assertFalse(result['complete'])
                self.assertEqual(result['n_returns'], count)
                self.assertIsNone(result['variance'])
                self.assertIsNone(result['volatility'])

    def test_coarse_bars_are_not_upsampled(self):
        rows = [
            {'t': START, 'c': 100},
            {'t': '2026-09-21T00:05:00Z', 'c': 200},
            {'t': '2026-09-21T00:10:00Z', 'c': 400},
        ]
        coarse = realized_volatility(
            rows, START, '2026-09-21T00:10:00Z', 300, 'end')
        fine = realized_volatility(
            rows, START, '2026-09-21T00:10:00Z', 60, 'end')
        self.assertTrue(coarse['complete'])
        self.assertAlmostEqual(coarse['variance'], 2 * math.log(2) ** 2, places=12)
        self.assertFalse(fine['complete'])
        self.assertEqual(fine['expected_returns'], 10)
        self.assertEqual(fine['n_returns'], 0)
        self.assertIsNone(fine['volatility'])

    def test_no_returns_is_missing(self):
        for rows in ([], minute_bars([100])):
            result = realized_volatility(
                rows, START, '2026-09-21T00:00:30Z', 60, 'end')
            self.assertFalse(result['complete'])
            self.assertEqual(result['expected_returns'], 0)
            self.assertEqual(result['n_returns'], 0)
            self.assertIsNone(result['variance'])

    def test_timezone_equivalence_and_no_mutation(self):
        rows = minute_bars([100, 110])
        original = [dict(row) for row in rows]
        result = realized_volatility(
            rows, '2026-09-21T01:00:00+01:00',
            '2026-09-21T01:01:00+01:00', 60, 'end')
        self.assertTrue(result['complete'])
        self.assertAlmostEqual(result['variance'], math.log(1.1) ** 2, places=12)
        self.assertEqual(rows, original)

    def test_invalid_prices(self):
        for price in (0, -1, True, '100', float('nan'), float('inf')):
            with self.subTest(price=price):
                with self.assertRaises(ValueError):
                    realized_volatility(
                        minute_bars([100, price]), START,
                        '2026-09-21T00:01:00Z', 60, 'end')

    def test_bad_order_duplicates_and_off_grid(self):
        rows = minute_bars([100, 110])
        cases = [rows[::-1], rows + [rows[-1]],
                 [{'t': '2026-09-21T00:00:30Z', 'c': 100}]]
        for supplied in cases:
            with self.subTest(supplied=supplied):
                with self.assertRaises(ValueError):
                    realized_volatility(
                        supplied, START, '2026-09-21T00:01:00Z', 60, 'end')

    def test_invalid_parameters(self):
        for seconds in (0, -60, 60.0, True):
            with self.subTest(seconds=seconds):
                with self.assertRaises(ValueError):
                    realized_volatility([], START, START, seconds, 'end')
        with self.assertRaises(ValueError):
            realized_volatility([], START, START, 60, 'guess')
        with self.assertRaises(ValueError):
            realized_volatility([], '2026-09-21T00:00:00', START, 60, 'end')
        with self.assertRaises(ValueError):
            realized_volatility([], START, '2026-09-20T23:59:00Z', 60, 'end')


if __name__ == '__main__':
    unittest.main()
