"""Known-value and point-in-time tests for the realized-volatility tool."""

import math
import unittest

from league.tools.realized_volatility import window_realized_volatility


START = '2026-09-21T12:00:00Z'
END = '2026-09-21T12:10:00Z'


def sample_bars():
    return [
        {'t': '2026-09-21T11:55:00Z', 'c': 100.0},
        {'t': '2026-09-21T12:00:00Z', 'c': 110.0},
        {'t': '2026-09-21T12:05:00Z', 'c': 99.0},
    ]


class TestWindowRealizedVolatility(unittest.TestCase):
    def test_known_values_and_no_mutation(self):
        bars = sample_bars()
        original = [dict(bar) for bar in bars]
        result = window_realized_volatility(bars, START, END)
        expected = math.log(1.1) ** 2 + math.log(0.9) ** 2
        self.assertAlmostEqual(result['realized_variance'], expected, places=14)
        self.assertAlmostEqual(result['realized_volatility'], math.sqrt(expected))
        self.assertAlmostEqual(result['rms_log_return'], math.sqrt(expected / 2))
        self.assertEqual(result['n_closes'], 3)
        self.assertEqual(result['n_returns'], 2)
        self.assertEqual(result['covered_seconds'], 600)
        self.assertTrue(result['complete'])
        self.assertEqual(bars, original)

    def test_not_demeaned_or_annualized(self):
        bars = sample_bars()
        for index, bar in enumerate(bars):
            bar['c'] = math.exp(index)
        result = window_realized_volatility(bars, START, END)
        self.assertAlmostEqual(result['realized_variance'], 2.0)
        self.assertAlmostEqual(result['realized_volatility'], math.sqrt(2))
        self.assertAlmostEqual(result['rms_log_return'], 1.0)

    def test_flat_path_is_zero_not_missing(self):
        bars = sample_bars()
        for bar in bars:
            bar['c'] = 100.0
        result = window_realized_volatility(bars, START, END)
        self.assertEqual(result['realized_variance'], 0.0)
        self.assertEqual(result['realized_volatility'], 0.0)
        self.assertEqual(result['rms_log_return'], 0.0)
        self.assertTrue(result['complete'])

    def test_empty_single_and_disconnected_closes_are_missing(self):
        bars = sample_bars()
        for selected in ([], bars[:1], [bars[0], bars[2]]):
            with self.subTest(selected=selected):
                result = window_realized_volatility(selected, START, END)
                self.assertIsNone(result['realized_variance'])
                self.assertIsNone(result['realized_volatility'])
                self.assertIsNone(result['rms_log_return'])
                self.assertEqual(result['n_returns'], 0)
                self.assertEqual(result['covered_seconds'], 0)
                self.assertFalse(result['complete'])

    def test_gap_is_not_bridged(self):
        bars = sample_bars()
        baseline = window_realized_volatility(bars, START, END)
        bars.append({'t': '2026-09-21T12:15:00Z', 'c': 198.0})
        result = window_realized_volatility(bars, START, '2026-09-21T12:20:00Z')
        self.assertEqual(result['n_closes'], 4)
        self.assertEqual(result['n_returns'], 2)
        self.assertEqual(result['covered_seconds'], 600)
        self.assertEqual(result['realized_variance'], baseline['realized_variance'])
        self.assertFalse(result['complete'])

    def test_unfinished_and_future_bars_are_excluded(self):
        bars = sample_bars()
        as_of = '2026-09-21T12:12:00Z'
        baseline = window_realized_volatility(bars, START, as_of)
        bars.extend([
            {'t': '2026-09-21T12:10:00Z', 'c': 1000000.0},
            {'t': '2026-09-21T12:15:00Z', 'c': 0.001},
        ])
        result = window_realized_volatility(bars, START, as_of)
        self.assertEqual(result, baseline)
        self.assertFalse(result['complete'])

    def test_return_cannot_cross_start(self):
        result = window_realized_volatility(
            sample_bars(), '2026-09-21T12:02:00Z', END)
        self.assertEqual(result['n_closes'], 2)
        self.assertEqual(result['n_returns'], 1)
        self.assertAlmostEqual(result['realized_variance'], math.log(0.9) ** 2)
        self.assertFalse(result['complete'])

    def test_absent_start_anchor_is_partial(self):
        result = window_realized_volatility(sample_bars()[1:], START, END)
        self.assertEqual(result['n_returns'], 1)
        self.assertEqual(result['covered_seconds'], 300)
        self.assertFalse(result['complete'])

    def test_explicit_end_stamps_and_timezone_offsets(self):
        end_stamped = [
            {'t': '2026-09-21T12:00:00Z', 'c': 100.0},
            {'t': '2026-09-21T12:05:00Z', 'c': 110.0},
            {'t': '2026-09-21T12:10:00Z', 'c': 99.0},
        ]
        expected = window_realized_volatility(sample_bars(), START, END)
        result = window_realized_volatility(
            end_stamped, '2026-09-21T08:00:00-04:00',
            '2026-09-21T08:10:00-04:00', timestamp_at='end')
        self.assertEqual(result, expected)

    def test_one_minute_cadence_uses_one_minute_inputs(self):
        bars = [
            {'t': '2026-09-21T11:59:00Z', 'c': 100.0},
            {'t': '2026-09-21T12:00:00Z', 'c': 110.0},
            {'t': '2026-09-21T12:01:00Z', 'c': 99.0},
        ]
        result = window_realized_volatility(
            bars, START, '2026-09-21T12:02:00Z', bar_seconds=60)
        self.assertEqual(result['n_returns'], 2)
        self.assertEqual(result['covered_seconds'], 120)
        self.assertTrue(result['complete'])
        self.assertAlmostEqual(
            result['realized_variance'], math.log(1.1) ** 2 + math.log(0.9) ** 2)

    def test_bad_prices(self):
        for bad in (0, -1, math.inf, math.nan, True, '100', None):
            with self.subTest(price=bad):
                bars = sample_bars()
                bars[1]['c'] = bad
                with self.assertRaises(ValueError):
                    window_realized_volatility(bars, START, END)

    def test_duplicate_reversed_and_naive_timestamps(self):
        bars = sample_bars()
        for bad_bars in (
            [bars[0], bars[0]],
            list(reversed(bars)),
            [{'t': '2026-09-21T12:00:00', 'c': 100.0}],
        ):
            with self.subTest(bars=bad_bars):
                with self.assertRaises(ValueError):
                    window_realized_volatility(bad_bars, START, END)

    def test_invalid_configuration(self):
        for cadence in (0, -1, 1.5, True):
            with self.subTest(cadence=cadence):
                with self.assertRaises(ValueError):
                    window_realized_volatility([], START, END, bar_seconds=cadence)
        for start, end in ((END, START), (START, START),
                           ('2026-09-21T12:00:00', END), ('invalid', END)):
            with self.subTest(start=start, end=end):
                with self.assertRaises(ValueError):
                    window_realized_volatility([], start, end)
        with self.assertRaises(ValueError):
            window_realized_volatility([], START, END, timestamp_at='middle')


if __name__ == '__main__':
    unittest.main()
