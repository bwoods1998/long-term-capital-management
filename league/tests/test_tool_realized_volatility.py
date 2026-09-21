"""Known-value and causal-coverage tests for the realized volatility tool."""

import math
import unittest

from league.tools.realized_volatility import window_realized_volatility


START = '2026-09-21T00:00:00Z'
END = '2026-09-21T00:15:00Z'


def start_bars():
    return [
        {'t': '2026-09-20T23:55:00Z', 'c': 100.0},
        {'t': '2026-09-21T00:00:00Z', 'c': 110.0},
        {'t': '2026-09-21T00:05:00Z', 'c': 99.0},
        {'t': '2026-09-21T00:10:00Z', 'c': 99.0},
    ]


def estimate(bars=None, as_of=END, bar_seconds=300, timestamp='start'):
    return window_realized_volatility(
        start_bars() if bars is None else bars,
        START, END, as_of, bar_seconds, timestamp,
    )


class RealizedVolatilityTests(unittest.TestCase):
    def test_known_log_returns(self):
        result = estimate()
        expected = math.log(1.1) ** 2 + math.log(0.9) ** 2
        self.assertAlmostEqual(result['realized_variance'], expected, places=14)
        self.assertAlmostEqual(result['realized_volatility'], math.sqrt(expected), places=14)
        self.assertEqual(result['return_count'], 3)
        self.assertEqual(result['expected_return_count'], 3)
        self.assertEqual(result['sample_count'], 4)
        self.assertEqual(result['bar_seconds'], 300)
        self.assertTrue(result['complete'])
        self.assertTrue(result['window_complete'])

    def test_flat_is_zero_not_missing(self):
        bars = [dict(bar, c=100.0) for bar in start_bars()]
        result = estimate(bars)
        self.assertEqual(result['realized_variance'], 0.0)
        self.assertEqual(result['realized_volatility'], 0.0)
        self.assertTrue(result['complete'])

    def test_fifteen_real_one_minute_returns(self):
        bars = [
            {'t': '2026-09-21T00:%02d:00Z' % minute, 'c': 100.0}
            for minute in range(16)
        ]
        result = estimate(bars, bar_seconds=60, timestamp='end')
        self.assertEqual(result['return_count'], 15)
        self.assertEqual(result['expected_return_count'], 15)
        self.assertEqual(result['sample_count'], 16)
        self.assertTrue(result['window_complete'])
        self.assertEqual(result['realized_volatility'], 0.0)

    def test_complete_prefix_excludes_unclosed_bars(self):
        now = '2026-09-21T00:07:00Z'
        result = estimate(as_of=now)
        self.assertAlmostEqual(result['realized_volatility'], math.log(1.1), places=14)
        self.assertEqual(result['expected_return_count'], 1)
        self.assertEqual(result['sample_count'], 2)
        self.assertTrue(result['complete'])
        self.assertFalse(result['window_complete'])
        bars = start_bars()
        changed_future = bars[:2] + [dict(bar, c=1e200) for bar in bars[2:]]
        self.assertEqual(result, estimate(changed_future, as_of=now))

    def test_missing_baseline_or_gap_is_not_a_low_estimate(self):
        bars = start_bars()
        for incomplete, count in ((bars[1:], 2), (bars[:2] + bars[3:], 1)):
            with self.subTest(count=count):
                result = estimate(incomplete)
                self.assertEqual(result['return_count'], count)
                self.assertEqual(result['expected_return_count'], 3)
                self.assertIsNone(result['realized_variance'])
                self.assertIsNone(result['realized_volatility'])
                self.assertFalse(result['complete'])
                self.assertFalse(result['window_complete'])

    def test_declaring_finer_cadence_does_not_create_samples(self):
        result = estimate(bar_seconds=60)
        self.assertEqual(result['expected_return_count'], 15)
        self.assertEqual(result['return_count'], 0)
        self.assertIsNone(result['realized_volatility'])

    def test_empty_and_zero_return_windows(self):
        self.assertIsNone(estimate([])['realized_volatility'])
        at_start = estimate(as_of=START)
        self.assertEqual(at_start['expected_return_count'], 0)
        self.assertEqual(at_start['sample_count'], 1)
        self.assertFalse(at_start['complete'])
        self.assertIsNone(at_start['realized_volatility'])
        before = estimate(as_of='2026-09-20T23:59:00Z')
        self.assertEqual(before['sample_count'], 0)
        self.assertEqual(before['expected_return_count'], 0)
        self.assertIsNone(before['realized_volatility'])

    def test_window_boundary_excludes_outside_prices(self):
        bars = [{'t': '2026-09-20T23:50:00Z', 'c': 1e200}]
        bars += start_bars()
        bars += [{'t': '2026-09-21T00:15:00Z', 'c': 1e200}]
        self.assertEqual(estimate(), estimate(bars, as_of='2026-09-21T00:30:00Z'))

    def test_end_labels_match_start_labels(self):
        bars = [
            {'t': '2026-09-21T00:%02d:00Z' % minute, 'c': price}
            for minute, price in ((0, 100.0), (5, 110.0), (10, 99.0), (15, 99.0))
        ]
        self.assertEqual(estimate(), estimate(bars, timestamp='end'))

    def test_timezone_equivalence(self):
        result = window_realized_volatility(
            start_bars(), '2026-09-21T02:00:00+02:00',
            '2026-09-21T02:15:00+02:00', '2026-09-21T02:15:00+02:00', 300,
        )
        self.assertEqual(estimate(), result)

    def test_invalid_selected_prices(self):
        for price in (0, -1, True, '100', None, float('nan'), float('inf'), -float('inf')):
            with self.subTest(price=price):
                bars = start_bars()
                bars[1] = dict(bars[1], c=price)
                with self.assertRaises(ValueError):
                    estimate(bars)

    def test_duplicate_reversed_and_off_grid_timestamps(self):
        bars = start_bars()
        invalid_sets = [
            bars[:1] + bars,
            list(reversed(bars)),
            [bars[0], dict(bars[1], t='2026-09-21T00:01:00Z')] + bars[2:],
        ]
        for invalid in invalid_sets:
            with self.assertRaises(ValueError):
                estimate(invalid)

    def test_invalid_options_and_times(self):
        for seconds in (0, -60, 60.0, True):
            with self.assertRaises(ValueError):
                estimate(bar_seconds=seconds)
        with self.assertRaises(ValueError):
            estimate(timestamp='guess')
        for time in ('2026-09-21T00:00:00', 'not-a-time', None):
            with self.assertRaises(ValueError):
                estimate(as_of=time)
        with self.assertRaises(ValueError):
            window_realized_volatility(start_bars(), END, START, END, 300)
        with self.assertRaises(ValueError):
            estimate(bar_seconds=120)

    def test_extreme_finite_prices_do_not_overflow_a_ratio(self):
        bars = start_bars()
        bars[0] = dict(bars[0], c=5e-324)
        bars[1] = dict(bars[1], c=1e308)
        result = estimate(bars)
        self.assertTrue(math.isfinite(result['realized_variance']))
        self.assertTrue(math.isfinite(result['realized_volatility']))

    def test_input_is_not_mutated(self):
        bars = start_bars()
        original = [dict(bar) for bar in bars]
        estimate(bars)
        self.assertEqual(bars, original)
